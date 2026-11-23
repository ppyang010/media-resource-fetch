#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
追更清单：记录「在追哪些剧」，让自动任务不依赖 prompt 里硬编码的剧名。

清单文件是 data/watchlist.json（可用 MEDIA_FETCH_DATA 改目录），
它是「追什么」的唯一事实来源。自动任务的 prompt 只负责说
「跑 watch.py due，逐条处理」，具体追哪些、什么规格、下次什么时候看，
全部读这个文件。

用法：
  python watch.py list                  # 看所有在追的（含最新集、下次到期）
  python watch.py list --all            # 连已暂停的也列出来
  python watch.py due                   # 只列现在到期该查的（自动任务第一步）
  python watch.py show --id jczcf-s4    # 看一条的完整配置

  python watch.py add --title "某某剧" --dir "/00影视-待看/某某剧" \
      --cadence "每晚 19:30 更 2 集" --next-due "2026-11-23 20:00"

  python watch.py done --id jczcf-s4 --episode "第8期上" --next-due "2026-11-28 12:00"
      # 补完后更新「已有到哪」，并算出下次什么时候再看

  python watch.py pending-add --id jczcf-s4 --file "第8期上.mp4" --got "906M 压缩版" --want "4K"
      # 先收了压缩版，记一笔待升级；自动任务下次会优先找更好的版本
  python watch.py pending-done --id jczcf-s4 --file "第8期上.mp4"
      # 升级完成（或决定不升级了），清掉这条待办

  python watch.py set --id jczcf-s4 --field active --value false   # 暂时不追了

判据（判断「到位」的标准）写在每条记录的 prefer 里：
  prefer.min_mb       —— 低于这个体积视为不完整/压缩版
  prefer.patterns     —— 文件名/目录名必须命中的关键词，如 ["4K","2160"]
  prefer.path         —— 多版本并列时限定父目录名子串，如 "60帧"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mplib as mp  # noqa: E402

DATA = mp.data_dir()
FILE = DATA / "watchlist.json"

TS_FMT = "%Y-%m-%d %H:%M"


def load() -> dict:
    if not FILE.exists():
        return {"version": 1, "updated": dt.date.today().isoformat(), "shows": []}
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated": dt.date.today().isoformat(), "shows": []}
    data.setdefault("shows", [])
    return data


def save(data: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    data["updated"] = dt.date.today().isoformat()
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_ts(text: str) -> dt.datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in (TS_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            t = dt.datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                t = t.replace(hour=21, minute=0)
            return t
        except ValueError:
            continue
    return None


def is_due(show: dict, now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now()
    t = parse_ts(str(show.get("next_due") or ""))
    return bool(t and now >= t)


def find(data: dict, key: str) -> dict | None:
    for s in data["shows"]:
        if key in (s.get("id"), s.get("title")):
            return s
    return None


def fmt_show(s: dict, mark_due: bool = True) -> str:
    flag = ""
    if s.get("active") is False:
        flag = " [暂停]"
    elif mark_due and is_due(s):
        flag = " [到期]"
    t = parse_ts(str(s.get("next_due") or ""))
    due = t.strftime("%m-%d %H:%M") if t else "—"
    pend = s.get("pending") or []
    lines = [
        f"{s.get('id',''):<14} {s.get('title','')}{flag}",
        f"   已有：{s.get('have') or '—'}",
        f"   下次：{due}   {s.get('cadence') or ''}",
        f"   目录：{s.get('dir','')}",
    ]
    if pend:
        lines.append("   待升级：")
        for p in pend:
            lines.append(f"     - {p.get('file','')}（现 {p.get('got','?')}，要 {p.get('want','?')}）")
    if s.get("note"):
        lines.append(f"   备注：{s['note']}")
    return "\n".join(lines)


# ---------------- 命令 ----------------

def cmd_list(args) -> int:
    data = load()
    shows = data["shows"]
    if not args.all:
        shows = [s for s in shows if s.get("active") is not False]
    if not shows:
        print("清单是空的。用 `watch.py add` 加一部，或 `--all` 看已暂停的。")
        return 0
    print(f"在追 {len(shows)} 部（清单文件 {FILE}）\n")
    for s in shows:
        print(fmt_show(s))
        print()
    return 0


def cmd_due(args) -> int:
    data = load()
    now = dt.datetime.now()
    due = [s for s in data["shows"] if s.get("active") is not False and is_due(s, now)]
    print(f"当前时间 {now.strftime(TS_FMT)}")
    if not due:
        nxt = [
            (parse_ts(str(s.get("next_due") or "")), s.get("title", ""))
            for s in data["shows"] if s.get("active") is not False
        ]
        nxt = [(t, n) for t, n in nxt if t]
        if nxt:
            t, n = min(nxt)
            print(f"没有到期任务。下次：「{n}」{t.strftime('%Y-%m-%d %H:%M')}")
        else:
            print("没有到期任务。")
        return 0
    print(f"到期 {len(due)} 部，逐条处理：\n")
    for s in due:
        print(fmt_show(s, mark_due=False))
        print()
    return 0


def cmd_show(args) -> int:
    data = load()
    s = find(data, args.id)
    if not s:
        print(f"没找到 {args.id}")
        return 1
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def cmd_add(args) -> int:
    data = load()
    sid = args.id or args.title
    if find(data, sid) or find(data, args.title):
        print(f"已存在：{args.title}，用 `watch.py set` 改，或先 rm")
        return 1
    show = {
        "id": sid,
        "title": args.title,
        "dir": args.dir,
        "active": True,
        "kind": args.kind or "series",
        "cadence": args.cadence or "",
        "next_due": args.next_due or "",
        "have": args.have or "",
        "keywords": [k for k in (args.keywords or "").split(",") if k],
        "prefer": {
            "label": args.prefer or "",
            "patterns": [p for p in (args.patterns or "").split(",") if p],
            "path": args.path or "",
            "min_mb": args.min_mb or 0,
        },
        "sources": [x for x in (args.sources or "weibo,jiugeku").split(",") if x],
        "pending": [],
        "note": args.note or "",
        "added": dt.date.today().isoformat(),
    }
    data["shows"].append(show)
    save(data)
    print(f"已加入追更清单：{show['title']}（{sid}）→ {FILE}")
    return 0


def cmd_set(args) -> int:
    data = load()
    s = find(data, args.id)
    if not s:
        print(f"没找到 {args.id}")
        return 1
    val = args.value
    if val.lower() in ("true", "false"):
        val = val.lower() == "true"
    elif val.isdigit():
        val = int(val)
    s[args.field] = val
    save(data)
    print(f"{s['title']} · {args.field} = {val}")
    return 0


def cmd_done(args) -> int:
    data = load()
    s = find(data, args.id)
    if not s:
        print(f"没找到 {args.id}")
        return 1
    if args.episode:
        s["have"] = args.episode
    if args.next_due:
        s["next_due"] = args.next_due
    s["last_check"] = dt.datetime.now().strftime(TS_FMT)
    save(data)
    print(f"{s['title']} 已更新：{s.get('have') or '—'}，下次 {s.get('next_due') or '—'}")
    return 0


def cmd_pending_add(args) -> int:
    data = load()
    s = find(data, args.id)
    if not s:
        print(f"没找到 {args.id}")
        return 1
    pend = s.setdefault("pending", [])
    if any(p.get("file") == args.file for p in pend):
        print(f"已有待升级项：{args.file}")
        return 0
    pend.append({
        "file": args.file,
        "got": args.got or "低规格版本",
        "want": args.want or (s.get("prefer") or {}).get("label") or "更高规格",
        "since": dt.date.today().isoformat(),
    })
    save(data)
    print(f"{s['title']} 记一笔待升级：{args.file}（{args.got} → {args.want}）")
    return 0


def cmd_pending_done(args) -> int:
    data = load()
    s = find(data, args.id)
    if not s:
        print(f"没找到 {args.id}")
        return 1
    pend = s.get("pending") or []
    keep = [p for p in pend if p.get("file") != args.file]
    s["pending"] = keep
    save(data)
    removed = len(pend) - len(keep)
    print(f"{s['title']} 已清掉 {removed} 条待升级" + (f"，剩 {len(keep)} 条" if keep else "，全部清完"))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="追更清单")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("list", help="列出在追的剧")
    a.add_argument("--all", action="store_true", help="连暂停的也列出")
    a.set_defaults(func=cmd_list)

    b = sub.add_parser("due", help="只列到期该查的")
    b.set_defaults(func=cmd_due)

    c = sub.add_parser("show", help="看一条的完整配置")
    c.add_argument("--id", required=True)
    c.set_defaults(func=cmd_show)

    d = sub.add_parser("add", help="加一部要追的")
    d.add_argument("--title", required=True)
    d.add_argument("--dir", required=True, help="网盘落盘目录")
    d.add_argument("--id", help="短 id，不给就用剧名")
    d.add_argument("--kind", choices=["variety", "series", "movie"])
    d.add_argument("--cadence", help="更新节奏，如「每晚 19:30 更 2 集」")
    d.add_argument("--next-due", help="下次该看的时间 YYYY-MM-DD HH:MM")
    d.add_argument("--have", help="已有进度，如「第7期下」")
    d.add_argument("--keywords", help="搜索关键词，逗号分隔")
    d.add_argument("--prefer", help="规格标签，如 4K")
    d.add_argument("--patterns", help="必须命中的关键词，逗号分隔")
    d.add_argument("--path", help="多版本并列时限定父目录名子串，如 60帧")
    d.add_argument("--min-mb", type=int, help="低于这个体积视为压缩版")
    d.add_argument("--sources", help="渠道，逗号分隔：weibo,jiugeku,kkpans")
    d.add_argument("--note", help="备注")
    d.set_defaults(func=cmd_add)

    e = sub.add_parser("set", help="改某个字段")
    e.add_argument("--id", required=True)
    e.add_argument("--field", required=True)
    e.add_argument("--value", required=True)
    e.set_defaults(func=cmd_set)

    f = sub.add_parser("done", help="标记补到哪一集，并设下次时间")
    f.add_argument("--id", required=True)
    f.add_argument("--episode", help="已有进度描述")
    f.add_argument("--next-due", help="下次该看的时间")
    f.set_defaults(func=cmd_done)

    g = sub.add_parser("pending-add", help="记一笔待升级（先收了压缩版）")
    g.add_argument("--id", required=True)
    g.add_argument("--file", required=True, help="已转存的文件名")
    g.add_argument("--got", help="现在的规格，如 906M 压缩版")
    g.add_argument("--want", help="想要的规格，如 4K")
    g.set_defaults(func=cmd_pending_add)

    h = sub.add_parser("pending-done", help="清掉待升级")
    h.add_argument("--id", required=True)
    h.add_argument("--file", required=True)
    h.set_defaults(func=cmd_pending_done)

    args = p.parse_args(argv[1:])
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv))
