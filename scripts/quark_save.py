#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克分享「选择性转存」：从分享里挑文件存进自己的网盘，不整包拉。

为什么不用「整包转存」：
  夸克原生的 save 接口若不带 fid_list，等于整个分享全量转存。
  遇到几十 G 的合集时没必要，这里显式指定要哪几个文件。

目录解析：
  直接调夸克 file/sort 逐级解析 fid，只依赖夸克 cookie，
  不需要任何外部软件在运行。

流程：
  1. GET  file/sort（drive-pc）      逐级把目标路径解析成 fid
  2. POST share/sharepage/token       拿 stoken
  3. GET  share/sharepage/detail      递归找目标文件的 fid + share_fid_token
  4. POST share/sharepage/save        fid_list 放要转的文件
  5. GET  task                        轮询转存任务

坑（都踩过）：
  - 所有请求必须带 pr=ucpro&fr=pc&uc_param_str=，少了 save 会 401 require login [guest]
  - save 的 stoken 不能留空
  - 读接口走 drive-h，写接口走 drive.quark.cn

用法：
  python quark_save.py <share_id或链接> <文件名关键词> <目标目录> [--all] [--dry]
  python quark_save.py 053c57393863 .mp4 "/00影视-待看" --all
  python quark_save.py 0c220e4f0c37 第四期上 "/00影视-待看" --dry
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://drive-h.quark.cn/1/clouddrive"
DRIVE_BASE = "https://drive-pc.quark.cn/1/clouddrive"
SAVE_BASE = "https://drive.quark.cn/1/clouddrive"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplib as mp  # noqa: E402


def quark(method: str, path: str, data: dict | None = None,
          params: dict | None = None, base: str = BASE) -> dict:
    """委托 mplib，cookie 由 mplib 统一管理（多来源兜底）。"""
    return mp.call(method, path, data=data, params=params, base=base)


def dir_fid(path: str) -> str:
    """把 /a/b 这样的路径逐级解析成目录 fid，不依赖外部软件。"""
    parts = [p for p in path.strip("/").split("/") if p]
    cur = "0"
    walked = ""
    for part in parts:
        res = quark("GET", "file/sort", params={
            "pdir_fid": cur, "_page": 1, "_size": 200,
            "_fetch_total": "1", "_sort": "file_type:asc,file_name:asc",
        }, base=DRIVE_BASE)
        if res.get("code") not in (0, None):
            raise SystemExit(f"列目录失败（fid={cur}）：{res.get('message') or res.get('code')}")
        found = None
        for f in (res.get("data") or {}).get("list") or []:
            if f.get("dir") and str(f.get("file_name")) == part:
                found = str(f.get("fid"))
        if not found:
            raise SystemExit(f"目录不存在：{(walked or '/')}/{part}")
        cur = found
        walked = f"{walked}/{part}"
    return cur


def find_files(share_id: str, keyword: str) -> tuple[list[dict], str]:
    """递归找文件名包含 keyword 的文件，返回 (命中列表, stoken)。"""
    tok = quark("POST", "share/sharepage/token", {
        "pwd_id": share_id, "passcode": "",
        "support_visit_limit_private_share": True,
    })
    stoken = (tok.get("data") or {}).get("stoken")
    if not stoken:
        raise SystemExit(f"分享无效：{tok.get('message') or tok.get('code')}")

    hits: list[dict] = []

    def walk(fid: str, depth: int) -> None:
        if depth > 4:
            return
        res = quark("GET", "share/sharepage/detail", params={
            "pwd_id": share_id, "stoken": stoken, "pdir_fid": fid,
            "force": "0", "_page": 1, "_size": 200,
            "_fetch_total": "1", "_sort": "file_type:asc,file_name:asc",
        })
        for f in (res.get("data") or {}).get("list") or []:
            name = str(f.get("file_name") or "")
            if f.get("dir"):
                walk(str(f.get("fid")), depth + 1)
            elif keyword in name:
                hits.append({
                    "fid": str(f.get("fid")),
                    "token": str(f.get("share_fid_token")),
                    "name": name,
                    "size": int(f.get("size") or 0),
                })

    walk("0", 1)
    if not hits:
        raise SystemExit(f"分享里没找到文件名包含「{keyword}」的文件")
    hits.sort(key=lambda x: x["name"])
    return hits, stoken


def save(share_id: str, stoken: str, files: list[dict], target_fid: str) -> dict:
    return quark("POST", "share/sharepage/save", {
        "fid_list": [f["fid"] for f in files],
        "fid_token_list": [f["token"] for f in files],
        "to_pdir_fid": target_fid,
        "pwd_id": share_id,
        "stoken": stoken,
        "pdir_fid": "0",
        "scene": "link",
    }, base=SAVE_BASE)


def human(size: int) -> str:
    return f"{size/1024**3:.2f}G" if size > 1024**3 else f"{size/1024**2:.0f}M"


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 0
    raw, keyword, target = argv[1], argv[2], argv[3]
    dry = "--dry" in argv
    take_all = "--all" in argv
    share_id = raw.rstrip("/").split("/")[-1].replace("s/", "")

    mp.init_cookie()
    print(f"分享 {share_id} → 目标 {target}")

    target_fid = dir_fid(target)
    print(f"目标目录 fid = {target_fid}")

    hits, stoken = find_files(share_id, keyword)
    for h in hits:
        print(f"  命中 {h['name']:<36} {human(h['size'])}")
    if not take_all:
        hits = hits[:1]
        print(f"（不加 --all 只转第一个：{hits[0]['name']}）")
    total = sum(h["size"] for h in hits)
    print(f"待转存 {len(hits)} 个文件，共 {human(total)}")

    if dry:
        print("--dry 模式，未执行转存")
        return 0

    res = save(share_id, stoken, hits, target_fid)
    print("转存返回：", json.dumps(res, ensure_ascii=False)[:220])
    task_id = (res.get("data") or {}).get("task_id")
    if not task_id:
        return 0 if res.get("code") == 0 else 1

    for i in range(20):
        time.sleep(1.5)
        st = quark("GET", "task", params={"task_id": task_id, "retry_index": i})
        data = st.get("data") or {}
        status = data.get("status")
        if status == 2:
            print("转存完成 ✅")
            return 0
        if status == 3:
            print(f"转存失败：{data.get('message') or st.get('message')}")
            return 1
    print("任务还在后台跑，稍后到网盘目录确认")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv))
