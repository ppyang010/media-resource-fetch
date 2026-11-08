#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公共层：配置定位、HTTP 调用、任务轮询。

这个 skill 是**独立单元**：不依赖任何外部软件、不依赖任何第三方库，
只靠 Python 3.8+ 标准库。整个目录拷到别的机器，配好 cookie 就能用。

夸克 cookie（两选一，先命中先用）：
  1. 环境变量 QUARK_COOKIE
  2. 配置文件 ~/.workbuddy/media-fetch.json 的 quark_cookie

数据目录（放 resources.jsonl / resources.md）：
  1. 环境变量 MEDIA_FETCH_DATA
  2. skill 内的 data/
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

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"

DRIVE = "https://drive-pc.quark.cn/1/clouddrive"
SHARE = "https://drive-h.quark.cn/1/clouddrive"
SAVE = "https://drive.quark.cn/1/clouddrive"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
PARAMS = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

COOKIE = ""
COOKIE_SOURCE = ""


# ---------------- 配置 ----------------

def config_path() -> Path:
    env = os.environ.get("MEDIA_FETCH_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".workbuddy" / "media-fetch.json"


def load_config() -> dict:
    p = config_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def init_cookie(required: bool = True) -> str:
    """按优先级取 cookie，写入模块级 COOKIE，并记住来源。"""
    global COOKIE, COOKIE_SOURCE
    candidates = [
        ("环境变量 QUARK_COOKIE", (os.environ.get("QUARK_COOKIE") or "").strip()),
        (f"配置文件 {config_path()}", str(load_config().get("quark_cookie") or "").strip()),
    ]
    for source, val in candidates:
        if val:
            COOKIE = val
            COOKIE_SOURCE = source
            return val
    if required:
        raise SystemExit(
            "找不到夸克授权。二选一：\n"
            "  1) 设置环境变量 QUARK_COOKIE=<cookie>\n"
            f"  2) 在 {config_path()} 里写 {{\"quark_cookie\": \"<cookie>\"}}\n"
            "获取 cookie：浏览器登录 pan.quark.cn → F12 → Network → 任一请求 → 复制整串 Cookie"
        )
    return ""


def data_dir() -> Path:
    env = os.environ.get("MEDIA_FETCH_DATA")
    if env:
        return Path(env).expanduser()
    return SKILL_ROOT / "data"


def choose_python() -> str:
    """给 subprocess 用。独立单元只认当前解释器，不再找外部 venv。"""
    return sys.executable


# ---------------- HTTP ----------------

def call(method: str, path: str, data: dict | None = None,
         params: dict | None = None, base: str = DRIVE) -> dict:
    q = dict(PARAMS)
    if params:
        q.update(params)
    url = f"{base}/{path}?{urllib.parse.urlencode(q)}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://pan.quark.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    if COOKIE:
        req.add_header("Cookie", COOKIE)
    req.add_header("x-requested-with", "XMLHttpRequest")
    if body:
        req.add_header("Content-Type", "application/json")
    with OPENER.open(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")


def anon_call(method: str, path: str, data: dict | None = None,
              params: dict | None = None, base: str = SHARE) -> dict:
    """不带 cookie 的调用（读分享不需要登录态）。"""
    global COOKIE
    saved, COOKIE = COOKIE, ""
    try:
        return call(method, path, data=data, params=params, base=base)
    finally:
        COOKIE = saved


def wait_task(task_id: str, label: str = "任务", timeout: int = 40) -> bool:
    for i in range(timeout):
        time.sleep(1.2)
        try:
            st = call("GET", "task", params={"task_id": task_id, "retry_index": i})
        except Exception:
            continue
        d = st.get("data") or {}
        if d.get("status") == 2:
            return True
        if d.get("status") == 3:
            print(f"   {label}失败：{d.get('message') or st.get('message')}")
            return False
    print(f"   {label}仍在后台跑，稍后到网盘确认")
    return True


# ---------------- 工具 ----------------

def human(size: int) -> str:
    return f"{size/1024**3:.2f}G" if size > 1024**3 else f"{size/1024**2:.0f}M"


def norm(f: dict) -> dict:
    """把 API 返回的条目统一成内部结构。"""
    return {
        "fid": str(f.get("fid")),
        "token": str(f.get("share_fid_token")),
        "name": str(f.get("file_name") or ""),
        "size": int(f.get("size") or 0),
        "dir": bool(f.get("dir")),
    }


def setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
