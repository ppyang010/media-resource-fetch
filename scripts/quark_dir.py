#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克网盘目录操作：建文件夹、移动文件、列目录、删除。只依赖标准库和夸克 cookie。

用法：
  python quark_dir.py mkdir "/00影视-待看/午夜规则"        # 逐级建，已存在就复用
  python quark_dir.py move "/00影视-待看" "/00影视-待看/午夜规则" 1.mp4 2.mp4 03.mp4
  python quark_dir.py ls "/00影视-待看/午夜规则"           # 看目录里有什么
  python quark_dir.py rm "/00影视-待看/某某" --yes          # 删除目录（含内容，必须 --yes）

端点（都带 pr=ucpro&fr=pc）：
  建目录  POST drive-pc /1/clouddrive/file
  移动    POST drive-pc /1/clouddrive/file/move   → task_id，需轮询 task
  列目录  GET  drive-pc /1/clouddrive/file/sort
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DRIVE = "https://drive-pc.quark.cn/1/clouddrive"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplib as mp  # noqa: E402


def call(method: str, path: str, data: dict | None = None,
         params: dict | None = None, base: str = DRIVE) -> dict:
    """委托 mplib，cookie 由 mplib 统一管理（多来源兜底）。"""
    return mp.call(method, path, data=data, params=params, base=base)


def list_dir(fid: str) -> list[dict]:
    res = call("GET", "file/sort", params={
        "pdir_fid": fid, "_page": 1, "_size": 200,
        "_fetch_total": "1", "_sort": "file_type:asc,file_name:asc",
    })
    if res.get("code") not in (0, None):
        raise SystemExit(f"列目录失败：{res.get('message') or res.get('code')}")
    return (res.get("data") or {}).get("list") or []


def resolve(path: str, create: bool = False) -> str:
    """逐级把路径解析成 fid；create=True 时缺失的层级会自动建。"""
    parts = [p for p in path.strip("/").split("/") if p]
    cur, walked = "0", ""
    for part in parts:
        found = None
        for f in list_dir(cur):
            if f.get("dir") and str(f.get("file_name")) == part:
                found = str(f.get("fid"))
        if not found:
            if not create:
                raise SystemExit(f"目录不存在：{walked}/{part}")
            res = call("POST", "file", {
                "pdir_fid": cur,
                "file_name": part,
                "dir_path": "",
                "dir_init_lock": False,
            })
            found = (res.get("data") or {}).get("fid")
            if not found:
                raise SystemExit(f"创建「{part}」失败：{res.get('message') or res.get('code')}")
            print(f"  已创建 {walked}/{part}  (fid={found})")
        cur = found
        walked = f"{walked}/{part}"
    return cur


def wait_task(task_id: str, label: str) -> bool:
    for i in range(20):
        time.sleep(1.2)
        st = call("GET", "task", params={"task_id": task_id, "retry_index": i})
        d = st.get("data") or {}
        if d.get("status") == 2:
            print(f"  {label}完成 ✅")
            return True
        if d.get("status") == 3:
            print(f"  {label}失败：{d.get('message') or st.get('message')}")
            return False
    print(f"  {label}任务还在跑，稍后到网盘确认")
    return True


def cmd_mkdir(argv: list[str]) -> int:
    if len(argv) < 1:
        print("用法：mkdir <路径>")
        return 1
    path = argv[0]
    print(f"创建目录 {path}")
    fid = resolve(path, create=True)
    print(f"目录就绪，fid = {fid}")
    return 0


def cmd_ls(argv: list[str]) -> int:
    path = argv[0] if argv else "/"
    fid = resolve(path)
    items = list_dir(fid)
    print(f"{path}（fid={fid}）共 {len(items)} 项：")
    for x in items:
        size = int(x.get("size") or 0)
        s = f"{size/1024**3:.2f}G" if size > 1024**3 else f"{size/1024**2:.0f}M"
        print(f"  {'DIR ' if x.get('dir') else 'FILE'} {str(x.get('file_name')):<40} {s}")
    return 0


def cmd_move(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法：move <源目录> <目标目录> <文件名...>")
        return 1
    src_path, dst_path, names = argv[0], argv[1], argv[2:]
    src_fid = resolve(src_path)
    dst_fid = resolve(dst_path)
    items = list_dir(src_fid)
    by_name = {str(x.get("file_name")): x for x in items}

    ids, missing = [], []
    for n in names:
        hit = by_name.get(n)
        if hit:
            ids.append(str(hit.get("fid")))
        else:
            missing.append(n)
    if missing:
        print(f"源目录里没找到：{', '.join(missing)}")
        print(f"可选：{', '.join(list(by_name)[:15])}")
        return 1

    print(f"移动 {len(ids)} 个文件：{src_path} → {dst_path}")
    # 坑：file/move 只认 filelist，不认 file_ids；
    # 且 filelist 与 current_dir_fid 是互斥的，一起传会报
    # 「[current_dir_fid,filelist 不能同时存在值]」。
    res = call("POST", "file/move", {
        "filelist": ids,
        "to_pdir_fid": dst_fid,
    })
    if res.get("code") not in (0, None):
        print("移动失败：", json.dumps(res, ensure_ascii=False)[:220])
        return 1
    task_id = (res.get("data") or {}).get("task_id")
    if task_id:
        wait_task(task_id, "移动")
    else:
        print("  移动完成（无 task_id）")
    return 0


def cmd_rm(argv: list[str]) -> int:
    """删除一个目录（含内容）。必须显式带 --yes，避免手滑。"""
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("用法：rm <路径> --yes")
        return 1
    path = args[0]
    if path.strip("/") == "":
        print("拒绝删除根目录")
        return 1
    if "--yes" not in argv:
        print(f"这会删除「{path}」及其全部内容。确认请重跑并加 --yes")
        return 1
    fid = resolve(path)
    res = call("POST", "file/delete", {"filelist": [fid]})
    if res.get("code") not in (0, None):
        print("删除失败：", json.dumps(res, ensure_ascii=False)[:200])
        return 1
    task_id = (res.get("data") or {}).get("task_id")
    if task_id:
        wait_task(task_id, "删除")
    print(f"已删除 {path}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    mp.init_cookie()
    cmd, rest = argv[1], argv[2:]
    if cmd == "mkdir":
        return cmd_mkdir(rest)
    if cmd == "ls":
        return cmd_ls(rest)
    if cmd == "move":
        return cmd_move(rest)
    if cmd == "rm":
        return cmd_rm(rest)
    print(__doc__)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv))
