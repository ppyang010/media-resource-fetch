#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本 skill 打包成一个可分发的 zip。

用法（在本文件所在目录执行）：
  python pack.py                # 打包，含台账数据
  python pack.py --no-data      # 打包，但不含 data/（不带私人记录）
  python pack.py --out D:\\tmp   # 指定输出目录

产物：dist/media-resource-fetch-<version>.zip + 同名 .sha256

分发出去的内容**不含**夸克 cookie（cookie 在 ~/.workbuddy/media-fetch.json，
不在 skill 目录内）。对方需要自己配一次。
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# 永远不打包的东西
EXCLUDE_DIRS = {"__pycache__", "dist", ".git", ".idea", ".vscode"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".zip", ".sha256"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def version() -> str:
    p = ROOT / "VERSION"
    return p.read_text(encoding="utf-8").strip() if p.is_file() else "0.0.0"


def collect(with_data: bool) -> list[Path]:
    files: list[Path] = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() in EXCLUDE_SUFFIX or p.name in EXCLUDE_FILES:
            continue
        if not with_data and rel.parts[0] == "data":
            continue
        files.append(p)
    return files


def human(n: int) -> str:
    return f"{n/1024:.0f} KB" if n < 1024 * 1024 else f"{n/1024/1024:.1f} MB"


def main(argv: list[str]) -> int:
    with_data = "--no-data" not in argv
    out_dir = DIST
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv):
            print("--out 需要跟一个目录")
            return 2
        out_dir = Path(argv[i + 1]).expanduser().resolve()

    ver = version()
    files = collect(with_data)
    if not files:
        print("没有可打包的文件")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"media-resource-fetch-{ver}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(ROOT)
            zf.write(f, Path("media-resource-fetch") / rel)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out_dir / f"{zip_path.name}.sha256").write_text(
        f"{digest}  {zip_path.name}\n", encoding="utf-8"
    )

    total = sum(f.stat().st_size for f in files)
    print(f"已打包 {len(files)} 个文件（原始 {human(total)}）")
    print(f"  {zip_path}  ({human(zip_path.stat().st_size)})")
    print(f"  sha256 {digest}")
    if not with_data:
        print("  注意：未包含 data/，对方从空台账开始")
    print()
    print("分发后对方怎么用：")
    print("  1. 解压，把 media-resource-fetch 文件夹放进 ~/.workbuddy/skills/")
    print("  2. cd 进去，运行 python install.py")
    print("  3. 按提示配夸克 cookie")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
