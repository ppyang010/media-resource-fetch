#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把电影资源台账同步成本 skill 内的资源库快照。

为什么要有这一步：
  台账（resources.jsonl）是原始数据，适合脚本读写但不适合人看。
  这里在 skill 内渲染一份**可读快照**，让人和 AI 都能直接看到"找过什么"。

  数据源仍然只有一份（jsonl），这里只做单向渲染，不反向写回，
  避免两边不一致。

用法：
  python sync_library.py
由 get.py 在写完台账后自动调用一次（找不到本脚本就跳过）。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mplib as mp  # noqa: E402

OUT = HERE.parent / "references" / "resource-library.md"
JSONL = mp.data_dir() / "resources.jsonl"

STATUS = {"ok": "✅ 在库", "dead": "❌ 已失效", "unknown": "❔ 未核验"}


def load() -> list[dict]:
    if not JSONL.is_file():
        return []
    rows = []
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def render(rows: list[dict]) -> str:
    saved = [r for r in rows if r.get("status") == "ok" and r.get("saved")]
    alive = [r for r in rows if r.get("status") == "ok" and not r.get("saved")]
    other = [r for r in rows if r.get("status") != "ok"]
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    def table(items: list[dict], with_path: bool) -> str:
        if not items:
            return "_（暂无）_\n"
        if with_path:
            head = ("| 片名 | 内容 | 网盘位置 | 来源 | 发布 | 备注 |",
                    "|:--|:--|:--|:--|:--|:--|")
        else:
            head = ("| 片名 | 内容 | 链接 | 状态 | 说明 |",
                    "|:--|:--|:--|:--|:--|")
        out = list(head)
        for r in items:
            if with_path:
                out.append("| {t} | {i} | {s} | {src} | {p} | {n} |".format(
                    t=r.get("title", ""), i=r.get("item", ""),
                    s=r.get("saved") or "—", src=r.get("source", ""),
                    p=r.get("published", ""), n=r.get("note") or "—"))
            else:
                out.append("| {t} | {i} | [{id}]({u}) | {st} | {n} |".format(
                    t=r.get("title", ""), i=r.get("item", ""),
                    id=r.get("id", ""), u=r.get("url", ""),
                    st=STATUS.get(r.get("status", "unknown"), "?"),
                    n=r.get("check_note") or r.get("note") or "—"))
        return "\n".join(out) + "\n"

    return f"""# 资源库（累积快照）

> 这个文件记录「已经找到并入过手」的影视资源，用来避免重复找、也方便回看来源。
> **由 `scripts/sync_library.py` 从台账自动生成，请勿手改**，手改会在下次同步时被覆盖。
> 数据源：`{JSONL}`
> 最后同步：{stamp}

## 概览

| 项 | 数量 |
|:--|:--|
| 累计找过 | {len(rows)} 部 |
| **已在网盘** | **{len(saved)} 部** |
| 链接有效但没转 | {len(alive)} 部 |
| 已失效（仅留档） | {len([r for r in other if r.get('status') == 'dead'])} 部 |

## 已在网盘

这些已经转存完毕，直接去网盘对应路径就能看，不需要再找。

{table(saved, True)}
## 链接还有效，但没转存

要的话随时可以用 `get.py` 补转，链接寿命约 6 天，别拖太久。

{table(alive, True)}
## 失效留档

链接过期是常态（微博来源约 6 天失效）。保留记录是为了知道
「哪些找过但没了」，不必重复去搜同一条 —— 直接找新的分享。

{table(other, False)}
## 维护

```powershell
cd "$env:USERPROFILE\\.workbuddy\\skills\\media-resource-fetch\\scripts"
python res.py check            # 先核验链接死活
python sync_library.py         # 再重渲染本文件
```

每次用 `get.py` 转存后会自动同步一次，通常不需要手动跑。
"""


def main() -> int:
    rows = load()
    if not rows:
        print(f"台账为空或不存在：{JSONL}")
        print("先用 res.py add 记一条，或跑一次 get.py 转存")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows), encoding="utf-8")
    saved = len([r for r in rows if r.get("status") == "ok" and r.get("saved")])
    print(f"已同步 {len(rows)} 条（已在网盘 {saved} 条）→ {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
