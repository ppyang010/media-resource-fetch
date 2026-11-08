#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微博检索：按关键词搜帖 / 按 uid 看博主更新 / 把帖子里的网盘直链挖出来。

为什么单独写一个：微博的免登录入口全灭（m.weibo.cn 432、s.weibo.com 302、
rsshub 403、weibo.com/u/ 跳 passport、sina.cn 镜像只认已知 uid 且会滞后）。
只有带登录态打 weibo.com 的 ajax 接口才稳定可用。

cookie（两选一，先命中先用）：
  1. 环境变量 WEIBO_COOKIE
  2. 配置文件 ~/.workbuddy/media-fetch.json 的 weibo_cookie

只需 SUB 和 SUBP 两个值：
  浏览器登录 weibo.com → F12 → Application → Cookies → https://weibo.com
  取 Domain 为 .weibo.com 的 SUB、SUBP，拼成 "SUB=xxx; SUBP=yyy"

用法：
  python weibo.py search <关键词> [--pages N] [--quark] [--json]
  python weibo.py user <uid>      [--pages N] [--quark]
  python weibo.py show <mid>
  python weibo.py check

关键坑（2026-11 实测）：
  - m.weibo.cn 不认 weibo.com 的 cookie，api/config 返回 login:false，别白折腾
  - 搜索接口 /ajax/statuses/search 返回的 text 里 t.cn 是占位/广告，直接 curl 会跳到
    广告页；真链接在 /ajax/statuses/show 的 url_struct[].long_url 里，必须二次请求
  - 搬运号爱把链接放评论区，而 buildComments 会过滤（"已过滤部分评论"），拿不到；
    优先找正文带「网页链接」的帖子
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplib  # noqa: E402

BASE = "https://weibo.com/ajax"
UA = mplib.UA
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

COOKIE = ""

# 正文里出现这些，才值得再发一次 show 请求去挖 long_url
LINK_HINTS = ("夸", "k：", "K：", "k:", "K:", "链接", "网页链接")


def init_cookie(required: bool = True) -> str:
    global COOKIE
    for source, val in (
        ("环境变量 WEIBO_COOKIE", (os.environ.get("WEIBO_COOKIE") or "").strip()),
        (f"配置文件 {mplib.config_path()}", str(mplib.load_config().get("weibo_cookie") or "").strip()),
    ):
        if val:
            COOKIE = val
            return val
    if required:
        raise SystemExit(
            "找不到微博授权。二选一：\n"
            "  1) 设置环境变量 WEIBO_COOKIE=\"SUB=xxx; SUBP=yyy\"\n"
            f"  2) 在 {mplib.config_path()} 里加 \"weibo_cookie\": \"SUB=xxx; SUBP=yyy\"\n"
            "获取：浏览器登录 weibo.com → F12 → Application → Cookies → https://weibo.com\n"
            "     取 Domain 为 .weibo.com 的 SUB 和 SUBP（SUB 是 HttpOnly，document.cookie 拿不到）"
        )
    return ""


def api(path: str, params: dict | None = None, retries: int = 3) -> dict:
    q = urllib.parse.urlencode(params or {})
    url = f"{BASE}/{path}" + (f"?{q}" if q else "")
    for i in range(retries):
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", "https://weibo.com/")
        req.add_header("Accept", "application/json, text/plain, */*")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        if COOKIE:
            req.add_header("Cookie", COOKIE)
        try:
            with OPENER.open(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", errors="ignore") or "{}")
        except urllib.error.HTTPError as e:
            if e.code in (418, 432) and i < retries - 1:
                time.sleep(2 + i * 2)
                continue
            raise SystemExit(f"微博接口 {path} 返回 HTTP {e.code}，cookie 可能失效，跑 weibo.py check")
        except Exception as e:
            if i < retries - 1:
                time.sleep(1.5)
                continue
            raise SystemExit(f"微博接口 {path} 请求失败：{e}")
    return {}


# ---------------- 解析 ----------------

def clean(text: str) -> str:
    t = re.sub(r"<br\s*/?>", " ", text or "")
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", t).strip()


def when(created_at: str) -> str:
    """'Sun Nov 08 20:30:36 +0800 2026' → '11-08 20:30'"""
    try:
        return time.strftime("%m-%d %H:%M", time.strptime(created_at, "%a %b %d %H:%M:%S %z %Y"))
    except Exception:
        return (created_at or "")[:16]


def link_targets(status: dict) -> dict:
    """拉帖子详情，返回 {'quark': [...], 'baidu': [...], 'other': [...]}。"""
    mid = status.get("mid") or status.get("idstr")
    out = {"quark": [], "baidu": [], "other": []}
    if not mid:
        return out
    try:
        det = api("statuses/show", {"id": mid, "isGetLongText": "true"})
    except SystemExit:
        raise
    for u in det.get("url_struct") or []:
        long_url = (u.get("long_url") or "").strip()
        if not long_url:
            continue
        if "pan.quark.cn" in long_url:
            out["quark"].append(long_url)
        elif "pan.baidu.com" in long_url:
            out["baidu"].append(long_url)
        elif long_url.startswith("http") and "weibo.com" not in long_url:
            out["other"].append(long_url)
    # 正文里直接写裸链接的也捞一遍
    raw = (det.get("text") or "") + (det.get("longText") or {}).get("longTextContent", "")
    for m in re.findall(r"https?://pan\.quark\.cn/s/[A-Za-z0-9]+", raw):
        if m not in out["quark"]:
            out["quark"].append(m)
    return out


def short_id(url: str) -> str:
    m = re.search(r"pan\.quark\.cn/s/([A-Za-z0-9]+)", url)
    return m.group(1) if m else ""


def enrich(statuses: Iterable[dict], only_quark: bool, as_json: bool) -> list:
    rows = []
    for s in statuses:
        text = clean(s.get("text") or "")
        has_hint = any(h in text for h in LINK_HINTS)
        links = link_targets(s) if has_hint else {"quark": [], "baidu": [], "other": []}
        if only_quark and not links["quark"]:
            continue
        rows.append({
            "time": when(s.get("created_at", "")),
            "user": (s.get("user") or {}).get("screen_name", ""),
            "uid": str((s.get("user") or {}).get("id", "")),
            "mid": str(s.get("mid") or s.get("idstr") or ""),
            "text": text,
            "quark": links["quark"],
            "baidu": links["baidu"],
        })
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return rows
    if not rows:
        print("（没有命中）")
        return rows
    for r in rows:
        print(f"[{r['time']}] @{r['user']} (uid {r['uid']})")
        print(f"   {r['text'][:110]}")
        for u in r["quark"]:
            print(f"   夸克 {u}   (id {short_id(u)})")
        for u in r["baidu"]:
            print(f"   百度 {u}")
        if not r["quark"] and not r["baidu"]:
            print("   （正文无直链，链接多半在评论区，已被过滤）")
        print(f"   mid {r['mid']}")
    print(f"\n共 {len(rows)} 条，其中带夸克链 {sum(1 for r in rows if r['quark'])} 条")
    return rows


# ---------------- 子命令 ----------------

def cmd_search(args) -> None:
    init_cookie()
    seen, bucket = set(), []
    for page in range(1, args.pages + 1):
        d = api("statuses/search", {"q": args.keyword, "page": page})
        sts = d.get("statuses") or []
        if not sts:
            break
        for s in sts:
            key = s.get("mid") or s.get("idstr")
            if key in seen:
                continue
            seen.add(key)
            bucket.append(s)
        if len(sts) < 10:
            break
    enrich(bucket, args.quark, args.json)


def cmd_user(args) -> None:
    init_cookie()
    bucket = []
    for page in range(1, args.pages + 1):
        d = api("statuses/mymblog", {"uid": args.uid, "page": page, "feature": 0})
        lst = (d.get("data") or {}).get("list") or []
        if not lst:
            break
        bucket.extend(lst)
        if len(lst) < 10:
            break
    if bucket:
        latest = when(bucket[0].get("created_at", ""))
        print(f"@{bucket[0].get('user', {}).get('screen_name', args.uid)} 最近一条 {latest}\n")
    enrich(bucket, args.quark, args.json)


def cmd_show(args) -> None:
    init_cookie()
    det = api("statuses/show", {"id": args.mid, "isGetLongText": "true"})
    enrich([det], False, args.json)


def cmd_check(args) -> None:
    ck = init_cookie()
    head = ck.split(";")[0]
    print(f"cookie：{head[:16]}…（共 {len(ck)} 字符，SUB+SUBP 齐全）")
    d = api("statuses/search", {"q": "现在就出发", "page": 1})
    sts = d.get("statuses") or []
    if not sts:
        raise SystemExit("接口通了但没结果，cookie 可能已失效")
    print(f"搜索接口 OK，返回 {len(sts)} 条，最新一条：{when(sts[0].get('created_at',''))}")
    print(f"   @{(sts[0].get('user') or {}).get('screen_name','')}  {clean(sts[0].get('text',''))[:50]}")


def main() -> None:
    mplib.setup_stdout()
    ap = argparse.ArgumentParser(
        description="微博检索：搜帖 / 看博主更新 / 挖帖子里的网盘直链",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd")

    p1 = sub.add_parser("search", help="按关键词搜帖")
    p1.add_argument("keyword")
    p1.add_argument("--pages", type=int, default=1)
    p1.add_argument("--quark", action="store_true", help="只显示带夸克链的")
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_search)

    p2 = sub.add_parser("user", help="看某 uid 最近的帖子")
    p2.add_argument("uid")
    p2.add_argument("--pages", type=int, default=1)
    p2.add_argument("--quark", action="store_true")
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(func=cmd_user)

    p3 = sub.add_parser("show", help="看单条帖子详情")
    p3.add_argument("mid")
    p3.add_argument("--json", action="store_true")
    p3.set_defaults(func=cmd_show)

    p4 = sub.add_parser("check", help="验证 cookie 是否可用")
    p4.set_defaults(func=cmd_check)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
