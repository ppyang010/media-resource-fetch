#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境自检：确认「找资源 → 转存」这条链路现在能不能跑。

检查五件事：
  1. 工具脚本是否齐（skill 自带，不需要外部目录）
  2. Python 版本是否够
  3. 数据目录是否可写（台账放哪）
  4. 夸克授权从哪来（环境变量 / 配置文件）
  5. cookie 是否真能列目录（不是只看非空）

用法：
  python check_env.py
退出码 0 = 全部就绪；1 = 有阻塞项
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplib as mp  # noqa: E402

NEEDED = ["get.py", "res.py", "quark_save.py", "quark_dir.py", "probe_share.py",
          "mplib.py", "sync_library.py", "weibo.py"]

problems: list[str] = []


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def bad(msg: str, block: bool = True) -> None:
    print(f"  [!!]   {msg}")
    if block:
        problems.append(msg)


def check_scripts() -> None:
    print("1) 工具脚本")
    missing = [n for n in NEEDED if not (mp.SCRIPTS / n).is_file()]
    if missing:
        bad(f"缺少：{', '.join(missing)}（skill 目录不完整）")
    else:
        ok(f"{mp.SCRIPTS}（{len(NEEDED)} 个齐备）")


def check_python() -> None:
    print("2) Python")
    v = sys.version_info
    if v >= (3, 9):
        ok(f"{v.major}.{v.minor}.{v.micro} —— {sys.executable}")
    elif v >= (3, 8):
        # 3.8 实测可跑（脚本都开了 from __future__ import annotations），只提示不阻塞
        print(f"  [--]   {v.major}.{v.minor}.{v.micro} —— {sys.executable}")
        print("         能用，但建议 3.9+；本机若装了新版可在 PATH 里切过去")
    else:
        bad(f"版本过低 {v.major}.{v.minor}，需要 3.9+")


def check_data() -> None:
    print("3) 数据目录")
    d = mp.data_dir()
    print(f"       位置：{d}")
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        ok("可写")
    except Exception as e:
        bad(f"不可写：{e}")
        return
    j = d / "resources.jsonl"
    if j.is_file():
        n = sum(1 for line in j.read_text(encoding="utf-8").splitlines() if line.strip())
        ok(f"已有台账 {n} 条")
    else:
        print("       （还没有台账，第一次转存会自动创建）")


def check_cookie() -> str:
    print("4) 夸克授权来源")
    p = mp.config_path()
    if (os.environ.get("QUARK_COOKIE") or "").strip():
        ok("来自环境变量 QUARK_COOKIE")
        return (os.environ.get("QUARK_COOKIE") or "").strip()
    if p.is_file():
        try:
            ck = str(json.loads(p.read_text(encoding="utf-8")).get("quark_cookie") or "").strip()
            if ck:
                ok(f"来自配置文件 {p}")
                return ck
        except Exception:
            bad(f"配置文件格式有问题：{p}")
    ck = str((mp.load_config().get("quark_cookie") or "")).strip()
    if ck:
        ok(f"来自配置文件 {p}")
        return ck
    bad(
        "没有找到夸克授权。二选一：\n"
        "   · 环境变量 QUARK_COOKIE=<cookie>\n"
        f"   · 在 {p} 写 {{\"quark_cookie\": \"<cookie>\"}}\n"
        "获取方式：浏览器登录 pan.quark.cn → F12 → Network → 任一请求 → 复制整串 Cookie"
    )
    return ""


def check_conn(ck: str) -> None:
    print("5) cookie 连通性")
    if not ck:
        print("       （跳过）")
        return
    q = dict(mp.PARAMS, pdir_fid="0", _page=1, _size=1, _fetch_total=1)
    url = f"{mp.DRIVE}/file/sort?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", mp.UA)
    req.add_header("Referer", "https://pan.quark.cn/")
    req.add_header("Cookie", ck)
    try:
        with mp.OPENER.open(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
    except urllib.error.HTTPError as e:
        bad(f"HTTP {e.code} —— cookie 可能失效，需要重新获取")
        return
    except Exception as e:
        bad(f"网络失败：{type(e).__name__}（检查系统代理）", block=False)
        return
    if data.get("code") not in (0, None):
        bad(f"返回 code={data.get('code')} {data.get('message')}")
        return
    ok("根目录可访问，授权有效")


def check_weibo() -> None:
    """微博是可选通道：没有它也能靠资源站干活，所以不阻塞。"""
    print("6) 微博授权（可选）")
    ck = (os.environ.get("WEIBO_COOKIE") or "").strip()
    src = "环境变量 WEIBO_COOKIE"
    if not ck:
        ck = str((mp.load_config().get("weibo_cookie") or "")).strip()
        src = f"配置文件 {mp.config_path()}"
    if not ck:
        print("       （未配置，只能用资源站和镜像页；配了可用 weibo.py search 直接搜帖）")
        return
    if "SUB=" not in ck:
        bad("cookie 里没有 SUB=，格式应为 \"SUB=xxx; SUBP=yyy\"", block=False)
        return
    ok(f"来自{src}")
    url = "https://weibo.com/ajax/statuses/search?" + urllib.parse.urlencode(
        {"q": "现在就出发", "page": 1})
    req = urllib.request.Request(url)
    for k, v in (("User-Agent", mp.UA), ("Referer", "https://weibo.com/"),
                 ("Accept", "application/json, text/plain, */*"),
                 ("X-Requested-With", "XMLHttpRequest"), ("Cookie", ck)):
        req.add_header(k, v)
    try:
        with mp.OPENER.open(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
    except urllib.error.HTTPError as e:
        bad(f"HTTP {e.code} —— cookie 可能失效，重新取一次 SUB/SUBP", block=False)
        return
    except Exception as e:
        bad(f"网络失败：{type(e).__name__}", block=False)
        return
    if not data.get("statuses"):
        bad("接口通了但没结果，cookie 可能过期", block=False)
        return
    ok(f"搜索接口有效，返回 {len(data['statuses'])} 条")


def main() -> int:
    print("影视资源查找/转存 —— 环境自检\n")
    check_scripts()
    check_python()
    check_data()
    ck = check_cookie()
    check_conn(ck)
    check_weibo()

    print()
    if problems:
        print("存在阻塞项，先解决：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("全部就绪，可以直接用 get.py 找片转存。")
    return 0


if __name__ == "__main__":
    mp.setup_stdout()
    sys.exit(main())
