#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一条命令把夸克分享同步进自己的网盘，并自动处理文件夹归属。

文件夹规则：
  · 分享根下本身就是一个剧名文件夹 → 沿用原名，整包转
  · 分享根下是散文件（或没有统一文件夹）→ 按剧名新建一个，全部放进去
  · 目标位置已存在同名文件夹 → 复用，不重复建
  · 分享是多部剧的大合集 → 必须 --pick 指定取哪一部

用法：
  python get.py <分享链接或id> [--name 剧名] [--dir /00影视-待看]
  python get.py 053c57393863 --name "午夜规则"
  python get.py 16f62cc22e64 --pick 会友 --name "后会友期"
  python get.py https://pan.quark.cn/s/053c57393863 --dry     # 只看计划

可选（都会写进台账）：
  --short "http://t.cn/xxx"   --source "微博 @某某"   --published "2026-11-05"
  --note "备注"               --no-log               不写台账
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplib as mp  # noqa: E402

HERE = Path(__file__).resolve().parent


# ---------------- 自己的网盘 ----------------

def my_list(fid: str) -> list[dict]:
    res = mp.call("GET", "file/sort", params={
        "pdir_fid": fid, "_page": 1, "_size": 200,
        "_fetch_total": "1", "_sort": "file_type:asc,file_name:asc",
    }, base=mp.DRIVE)
    if res.get("code") not in (0, None):
        raise SystemExit(f"列目录失败：{res.get('message') or res.get('code')}")
    return (res.get("data") or {}).get("list") or []


def resolve(path: str, create: bool = False) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    cur, walked = "0", ""
    for part in parts:
        found = None
        for f in my_list(cur):
            if f.get("dir") and str(f.get("file_name")) == part:
                found = str(f.get("fid"))
        if not found:
            if not create:
                raise SystemExit(f"目录不存在：{walked}/{part}")
            res = mp.call("POST", "file", {
                "pdir_fid": cur, "file_name": part,
                "dir_path": "", "dir_init_lock": False,
            }, base=mp.DRIVE)
            found = (res.get("data") or {}).get("fid")
            if not found:
                raise SystemExit(f"创建「{part}」失败：{res.get('message') or res.get('code')}")
            print(f"   已创建目录 {walked}/{part}")
        cur = found
        walked = f"{walked}/{part}"
    return cur


# ---------------- 分享 ----------------

def share_token(sid: str) -> str:
    tok = mp.call("POST", "share/sharepage/token", {
        "pwd_id": sid, "passcode": "",
        "support_visit_limit_private_share": True,
    }, base=mp.SHARE)
    st = (tok.get("data") or {}).get("stoken")
    if not st:
        raise SystemExit(f"分享无效或已失效：{tok.get('message') or tok.get('code')}")
    return st


def share_list(sid: str, stoken: str, fid: str) -> dict:
    return mp.call("GET", "share/sharepage/detail", params={
        "pwd_id": sid, "stoken": stoken, "pdir_fid": fid,
        "force": "0", "_page": 1, "_size": 200,
        "_fetch_banner": "1", "_fetch_share": "1", "_fetch_total": "1",
        "_sort": "file_type:asc,file_name:asc",
    }, base=mp.SHARE).get("data") or {}


def walk_all(sid: str, stoken: str, fid: str, depth: int = 0) -> list[dict]:
    """递归收集所有文件和目录（带 token），用于统计和逐文件转存。"""
    out: list[dict] = []
    if depth > 5:
        return out
    for f in share_list(sid, stoken, fid).get("list") or []:
        item = mp.norm(f)
        out.append(item)
        if item["dir"]:
            out.extend(walk_all(sid, stoken, item["fid"], depth + 1))
    return out


def clean_name(title: str) -> str:
    """把分享标题收拾成像样的文件夹名。"""
    t = re.sub(r"[\\/:*?\"<>|]", " ", title or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t[:60] or "未命名"


# ---------------- 转存 ----------------

def transfer(sid: str, stoken: str, items: list[dict], to_fid: str) -> bool:
    res = mp.call("POST", "share/sharepage/save", {
        "fid_list": [i["fid"] for i in items],
        "fid_token_list": [i["token"] for i in items],
        "to_pdir_fid": to_fid,
        "pwd_id": sid,
        "stoken": stoken,
        "pdir_fid": "0",
        "scene": "link",
    }, base=mp.SAVE)
    if res.get("code") not in (0, None):
        print(f"   转存失败：{json_cut(res)}")
        return False
    tid = (res.get("data") or {}).get("task_id")
    if not tid:
        return True
    return mp.wait_task(tid, "转存")


def transfer_robust(sid: str, stoken: str, items: list[dict], to_fid: str,
                    flat: list[dict] | None = None) -> bool:
    """转存；如果因为含目录而失败，退化成展开成文件逐个转。"""
    if transfer(sid, stoken, items, to_fid):
        return True
    if not flat or not any(i["dir"] for i in items):
        return False
    print("   含目录的方式没成功 → 改为展开成文件逐个转")
    return transfer(sid, stoken, flat, to_fid)


def json_cut(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)[:200]


def count_files(items: list[dict]) -> tuple[int, int]:
    files = [i for i in items if not i["dir"]]
    return len(files), sum(i["size"] for i in files)


# ---------------- 主流程 ----------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("target", help="分享链接或 share_id")
    ap.add_argument("--name", help="剧名（分享里没有统一文件夹时用它新建）")
    ap.add_argument("--pick", help="合集分享里只取名字含该关键词的子目录/文件")
    ap.add_argument("--dir", default="/00影视-待看", help="同步到哪个目录，默认 /00影视-待看")
    ap.add_argument("--dry", action="store_true", help="只看计划，不真转")
    ap.add_argument("--short", default="", help="微博短链等原始入口")
    ap.add_argument("--source", default="", help="来源，如「微博 @某某」")
    ap.add_argument("--published", default="", help="资源发布时间")
    ap.add_argument("--note", default="", help="备注")
    ap.add_argument("--no-log", action="store_true", help="不写台账")
    args = ap.parse_args(argv[1:])

    sid = args.target.rstrip("/").split("/")[-1].replace("s/", "")
    mp.init_cookie()

    print(f"分享 {sid}")
    stoken = share_token(sid)
    root = share_list(sid, stoken, "0")
    share_title = (root.get("share") or {}).get("title") or ""
    top = [mp.norm(f) for f in root.get("list") or []]
    dirs = [x for x in top if x["dir"]]
    plain = [x for x in top if not x["dir"]]

    if share_title:
        print(f"  分享标题：{share_title}")

    # ---- --pick：从合集分享里只取一个子目录/文件 ----
    picked_dir: dict | None = None
    picked_files: list[dict] = []
    if args.pick:
        cands = [x for x in top if args.pick in x["name"]]
        cand_dirs = [x for x in cands if x["dir"]]
        if cand_dirs:
            picked_dir = cand_dirs[0]
        elif cands:
            picked_files = cands
        else:
            print(f"  分享里找不到名字含「{args.pick}」的项。可选：")
            for x in top:
                print(f"    {'DIR ' if x['dir'] else 'FILE'} {x['name']}")
            return 1

    # ---- 判定归属方式 ----
    # keep   分享里就是一个干净的剧名文件夹 → 整包转，沿用原名
    # rename 分享里有文件夹但名字不理想（如规避审查插字），用 --name 重建
    # new    分享里是散文件，按剧名新建
    # pick   合集分享里只取指定的一项（--pick），其余不要
    if picked_dir or picked_files:
        target = picked_dir or picked_files[0]
        mode = "pick"
        folder = clean_name(args.name or target["name"])
        kind = "目录" if picked_dir else "文件"
        print(f"  结构：合集{kind}「{target['name']}」→ 只取它，放入「{folder}」")
        if not args.name:
            print("        （名字取自该合集项，不理想可用 --name 覆盖）")
    elif len(dirs) == 1 and not plain:
        original = dirs[0]["name"]
        if args.name and clean_name(args.name) != clean_name(original):
            mode, folder = "rename", clean_name(args.name)
            print(f"  结构：单个文件夹「{original}」→ 用 --name 改名为「{folder}」")
        else:
            mode, folder = "keep", original
            print(f"  结构：单个剧名文件夹「{folder}」→ 沿用原文件夹名")
    else:
        mode = "new"
        folder = clean_name(args.name or share_title)
        print(f"  结构：{len(dirs)} 个目录 + {len(plain)} 个散文件 → 按剧名新建「{folder}」")
        if not args.name:
            print("        （名字取自分享标题，不理想可用 --name 覆盖）")
        if len(dirs) > 1:
            print("        提示：这看着像合集，只想取其中一个就加 --pick <名字关键词>")

    parent = args.dir.rstrip("/")
    target_path = f"{parent}/{folder}"

    if mode == "pick":
        if picked_dir:
            inner = [mp.norm(f) for f in share_list(sid, stoken, picked_dir["fid"]).get("list") or []]
            top_items = inner
            all_items = inner + [i for d in inner if d["dir"]
                                 for i in walk_all(sid, stoken, d["fid"])]
        else:
            top_items = picked_files
            all_items = picked_files
    elif mode == "rename":
        # 只取这个文件夹的直接内容，避免多套一层
        top_items = [mp.norm(f) for f in share_list(sid, stoken, dirs[0]["fid"]).get("list") or []]
        all_items = top_items + [i for d in top_items if d["dir"]
                                 for i in walk_all(sid, stoken, d["fid"])]
    else:
        top_items = top
        all_items = walk_all(sid, stoken, "0")

    nfile, total = count_files(all_items)
    print(f"  内容：{nfile} 个文件，共 {mp.human(total)}")

    if not top_items:
        print("\n这个分享里取不到内容（可能已失效、需要提取码，或被限制转存）。已中止，未建文件夹。")
        return 1

    if args.dry:
        print(f"\n[计划] 目标位置 {target_path}")
        if mode == "keep":
            print(f"       把该文件夹整体转存到 {parent}")
        elif mode == "rename":
            print(f"       新建「{folder}」，把原文件夹里的内容搬进去（不多套一层）")
        elif mode == "pick":
            print(f"       新建「{folder}」，只把合集里挑中的那一项内容放进去")
        else:
            print("       新建文件夹后，把全部内容转存进去")
        print("[dry] 未执行")
        return 0

    # ---- 执行 ----
    print(f"\n同步到 {target_path}")
    parent_fid = resolve(parent, create=True)

    existing = None
    for f in my_list(parent_fid):
        if f.get("dir") and str(f.get("file_name")) == folder:
            existing = str(f.get("fid"))

    folder_fid = None
    flat = [i for i in all_items if not i["dir"]]
    if mode == "keep":
        if existing:
            # 已存在同名文件夹：把原文件夹的直接内容并入（保留内部子目录结构），
            # 避免夸克另外建一个「xxx(1)」
            print("   同名文件夹已存在 → 内容并入，不新建")
            folder_fid = existing
            inner_items = [mp.norm(f) for f in share_list(sid, stoken, dirs[0]["fid"]).get("list") or []]
            if inner_items and transfer_robust(sid, stoken, inner_items, folder_fid, flat):
                print(f"   已并入 {len(inner_items)} 项")
        else:
            # 整体转存这个目录，夸克会以原名建成 parent/folder
            if transfer_robust(sid, stoken, [dirs[0]], parent_fid, None):
                print(f"   已转存文件夹「{folder}」")
                folder_fid = None
            else:
                # 整包失败 → 自己建同名目录再塞文件
                print("   整包转存失败 → 新建同名目录后逐个转")
                folder_fid = resolve(target_path, create=True)
                if transfer(sid, stoken, flat, folder_fid):
                    print(f"   已转存 {len(flat)} 个文件")
    else:
        folder_fid = existing or resolve(target_path, create=True)
        # 只转顶层：目录会被整体带入，再传它内部的文件会重复
        if transfer_robust(sid, stoken, top_items, folder_fid, flat):
            print(f"   已转存 {len(top_items)} 项")

    # ---- 校验 ----
    if folder_fid:
        try:
            print(f"   目录现有 {len(my_list(folder_fid))} 项")
        except Exception:
            pass

    # ---- 记台账 ----
    if not args.no_log:
        cmd = [mp.choose_python(), str(HERE / "res.py"), "add",
               "--title", folder,
               "--item", f"{nfile} 个文件 / {mp.human(total)}",
               "--url", f"https://pan.quark.cn/s/{sid}",
               "--saved", target_path + "/",
               "--note", args.note or "由 get.py 自动记录"]
        for flag, val in (("--short", args.short), ("--source", args.source),
                          ("--published", args.published)):
            if val:
                cmd += [flag, val]
        try:
            r = subprocess.run(cmd, cwd=str(HERE), check=False,
                               capture_output=True, text=True, encoding="utf-8")
            print("   已写入台账 resources.md" if r.returncode == 0 else
                  f"   台账写入异常：{(r.stderr or '')[:120]}")
        except Exception as e:
            print(f"   台账写入失败（不影响文件）：{e}")

        # 顺手刷新 skill 里的资源库快照
        lib = HERE / "sync_library.py"
        if lib.is_file():
            try:
                subprocess.run([mp.choose_python(), str(lib)], check=False,
                               capture_output=True, text=True, encoding="utf-8")
                print("   已同步资源库快照")
            except Exception:
                pass

    print("\n完成。")
    return 0


if __name__ == "__main__":
    mp.setup_stdout()
    sys.exit(main(sys.argv))
