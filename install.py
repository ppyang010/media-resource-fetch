#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装向导：把本 skill 放到 ~/.workbuddy/skills/ 并检查授权是否就绪。

用法（在解压出来的 media-resource-fetch 目录里执行）：
  python install.py            # 安装 / 就地检查
  python install.py --force    # 目标已存在时覆盖（会先备份）

安装目标：~/.workbuddy/skills/media-resource-fetch
配置文件：~/.workbuddy/media-fetch.json（cookie 只存这里，不随 skill 分发）

安装是幂等的：如果当前目录已经是目标目录，只做检查，不会自我复制。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
NAME = "media-resource-fetch"
DEST_ROOT = Path.home() / ".workbuddy" / "skills"
DEST = DEST_ROOT / NAME
CONFIG = Path.home() / ".workbuddy" / "media-fetch.json"

SKIP_DIRS = {"__pycache__", "dist", ".git"}
SKIP_SUFFIX = {".pyc", ".pyo"}


def say(msg: str = "") -> None:
    print(msg, flush=True)


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIX:
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        n += 1
    return n


def install(force: bool) -> Path:
    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    if SRC == DEST.resolve():
        say(f"当前目录就是安装位置，跳过复制：{DEST}")
        return DEST

    if DEST.exists():
        if not force:
            say(f"目标已存在：{DEST}")
            say("如果确认要覆盖，加 --force（会先把旧版本备份到 *.bak-<时间戳>）")
            return DEST
        import datetime as dt
        bak = DEST.with_name(f"{NAME}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.move(str(DEST), str(bak))
        say(f"旧版本已备份到 {bak}")

    n = copy_tree(SRC, DEST)
    say(f"已安装 {n} 个文件 → {DEST}")
    return DEST


def check_cookie() -> bool:
    say()
    say("--- 夸克授权 ---")
    if (os.environ.get("QUARK_COOKIE") or "").strip():
        say("[OK] 环境变量 QUARK_COOKIE 已设置")
        return True

    cfg = {}
    if CONFIG.is_file():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    if str(cfg.get("quark_cookie") or "").strip():
        say(f"[OK] 配置文件已有 cookie：{CONFIG}")
        return True

    say("[!!] 还没有配夸克 cookie。获取方式：")
    say("     1. 浏览器打开 pan.quark.cn 并登录")
    say("     2. F12 → Network → 随便点一个请求 → 复制整串 Cookie")
    say(f"     3. 写进 {CONFIG}：")
    say('        {"quark_cookie": "粘贴到这里"}')

    if sys.stdin.isatty():
        say()
        say("也可以现在直接粘贴 cookie（留空则跳过）：")
        try:
            val = input("Cookie> ").strip()
        except EOFError:
            val = ""
        if val:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            cfg["quark_cookie"] = val
            cfg.setdefault("default_dir", "/00影视-待看")
            CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            try:
                os.chmod(CONFIG, 0o600)
            except Exception:
                pass
            say(f"[OK] 已写入 {CONFIG}")
            return True
    else:
        say("     （当前非交互模式，跳过输入）")
    return False


def run_selfcheck(target: Path) -> int:
    say()
    say("--- 环境自检 ---")
    script = target / "scripts" / "check_env.py"
    if not script.is_file():
        say(f"[!!] 找不到 {script}")
        return 1
    return subprocess.call([sys.executable, str(script)], cwd=str(script.parent))


def main(argv: list[str]) -> int:
    force = "--force" in argv
    say(f"安装 {NAME} → {DEST}")
    target = install(force)

    has_cookie = check_cookie()
    code = run_selfcheck(target)

    say()
    if code == 0:
        say("安装完成。可以直接说「帮我找某部剧」，或手动：")
        say(f'  cd "{target / "scripts"}"')
        say("  python get.py <share_id> --dry")
    elif not has_cookie:
        say("文件已就位，但缺夸克授权。配好 cookie 后重跑：")
        say(f'  python "{target / "scripts" / "check_env.py"}"')
        return 1
    else:
        say("文件已就位，但自检未通过，看上面的阻塞项。")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
