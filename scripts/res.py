#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资源台账工具：把找到的网盘资源记下来，并定期核验是否还有效。

数据源是 resources.jsonl（一行一条，真源），resources.md 由本脚本渲染，
**不要手改 md**，改了下次渲染会被覆盖。

用法：
  python res.py add --title "现在就出发 第四季" --item "第5期" \
      --url https://pan.quark.cn/s/xxxx --source "微博 @某某" --published "2026-11-01"
  python res.py list             # 看台账
  python res.py check            # 逐条核验有效/失效，自动更新状态并重渲染 md
  python res.py render           # 只重渲染 md
  python res.py check --id xxxx  # 只查某一条

status 取值：ok（有效）/ dead（失效）/ unknown（未核验）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mplib as mp  # noqa: E402

# 台账位置由 mplib 决定：MEDIA_FETCH_DATA → skill/data
DATA = mp.data_dir()
JSONL = DATA / "resources.jsonl"
MD = DATA / "resources.md"

BASE = "https://drive-h.quark.cn/1/clouddrive"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

STATUS_LABEL = {"ok": "✅ 有效", "dead": "❌ 失效", "unknown": "❔ 未核验"}


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------- 读写 ----------

def load() -> list[dict]:
    if not JSONL.exists():
        return []
    rows = []
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def save(rows: list[dict]) -> None:
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    JSONL.write_text(text, encoding="utf-8")


def share_id(item: dict) -> str:
    if item.get("id"):
        return str(item["id"])
    url = str(item.get("url") or "")
    return url.rstrip("/").split("/")[-1]


# ---------- 核验 ----------

def probe(sid: str) -> tuple[str, str]:
    """返回 (status, 说明)。只看 token 接口能否拿到 stoken。"""
    try:
        body = json.dumps({
            "pwd_id": sid,
            "passcode": "",
            "support_visit_limit_private_share": True,
        }).encode()
        req = urllib.request.Request(f"{BASE}/share/sharepage/token", data=body, method="POST")
        req.add_header("User-Agent", UA)
        req.add_header("Referer", "https://pan.quark.cn/")
        req.add_header("Content-Type", "application/json")
        with OPENER.open(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
    except urllib.error.HTTPError as e:
        return "dead", f"HTTP {e.code}"
    except Exception as e:
        return "unknown", f"网络异常：{type(e).__name__}"

    if (data.get("data") or {}).get("stoken"):
        return "ok", "正常"
    msg = str(data.get("message") or data.get("msg") or "")
    code = data.get("code")
    if "passcode" in msg.lower() or code in (41004, 41008):
        return "ok", f"需提取码（code={code}）"
    return "dead", f"无 stoken（code={code} {msg}）"


def cmd_check(args) -> int:
    rows = load()
    if not rows:
        print("台账是空的")
        return 0
    stamp = now()
    changed = 0
    for item in rows:
        sid = share_id(item)
        if args.id and args.id not in (sid, item.get("title")):
            continue
        if item.get("kind", "quark") != "quark":
            continue
        st, why = probe(sid)
        old = item.get("status")
        item["status"] = st
        item["checked_at"] = stamp
        item["check_note"] = why
        if old != st:
            changed += 1
        print(f"  {STATUS_LABEL.get(st, st):<8} {item.get('title','')[:16]:<18} "
              f"{str(item.get('item',''))[:26]:<28} {why}")
    save(rows)
    render(rows)
    print(f"\n核验完成：{len(rows)} 条，状态变化 {changed} 条。台账已更新 {MD.name}")
    return 0


# ---------- 展示 ----------

def render(rows: list[dict]) -> None:
    ok = [r for r in rows if r.get("status") == "ok"]
    rest = [r for r in rows if r.get("status") != "ok"]

    def table(items: list[dict]) -> str:
        if not items:
            return "_（暂无）_\n"
        out = [
            "| 片名 | 内容 | 链接 | 来源 | 发布 | 已转存 | 备注 |",
            "|:--|:--|:--|:--|:--|:--|:--|",
        ]
        for r in items:
            url = r.get("url") or ""
            short = r.get("short") or ""
            link = f"[{share_id(r)}]({url})" + (f"<br>`{short}`" if short else "")
            out.append(
                "| {title} | {item} | {link} | {source} | {pub} | {saved} | {note} |".format(
                    title=r.get("title", ""),
                    item=r.get("item", ""),
                    link=link,
                    source=r.get("source", ""),
                    pub=r.get("published", ""),
                    saved=r.get("saved") or "—",
                    note=r.get("note") or "—",
                )
            )
        return "\n".join(out) + "\n"

    checked = [r.get("checked_at") for r in rows if r.get("checked_at")]
    last = max(checked) if checked else "尚未核验"

    md = f"""# 资源台账

> 记录找到的网盘资源，避免链接失效后找不到出处。
> **数据源是 `resources.jsonl`，本文件由 `python res.py render` 生成，请勿手改。**
> 最后核验：{last}

## 快速用法

```powershell
python res.py add --title "片名" --item "第N期" --url "https://pan.quark.cn/s/xxxx" --source "微博 @某某" --published "2026-11-01"
python res.py list      # 看台账
python res.py check     # 核验全部链接是否还有效
python res.py rm --id 0c220e4f0c37   # 删一条
```

转存单文件用 `quark_save.py`，先看分享里有什么用 `probe_share.py`。

## ✅ 有效（{len(ok)}）

{table(ok)}
## ❌ 失效 / ❔ 未核验（{len(rest)}）

{table(rest)}
## 经验

- **微博类分享寿命约 6 天**。两个独立样本：10-25 发的链接 10-31 失效、10-31 发的 11-06 失效。看到就转，别存链接。
- 找片套路：WebSearch 确认剧名和更新进度 → 抓 `sina.cn/media/<uid>` 微博镜像页拿 `t.cn` 短链（免登录）→ 解短链得 `pan.quark.cn/s/<id>` → `probe_share.py` 验内容 → `quark_save.py` 转存。
- 微博短链（`t.cn`）用 `curl -o /dev/null -w "%{{redirect_url}}"` 就能解出真实地址，不用登录。
- 小雅索引里夸克占比低（`quarkshare_list.txt` 只有 58 个合集），新片基本搜不到，还是得靠微博 / Telegram。
"""
    MD.write_text(md, encoding="utf-8")


def cmd_list(args) -> int:
    rows = load()
    if not rows:
        print("台账是空的，先 add 一条")
        return 0
    print(f"共 {len(rows)} 条\n")
    for r in rows:
        st = STATUS_LABEL.get(r.get("status", "unknown"), "?")
        print(f"{st}  {r.get('title','')}")
        print(f"      {r.get('item','')}")
        print(f"      {r.get('url','')}   {r.get('short','')}")
        print(f"      来源 {r.get('source','—')} | 发布 {r.get('published','—')} | 记录 {r.get('added','—')}")
        if r.get("saved"):
            print(f"      已转存 → {r['saved']}")
        if r.get("note"):
            print(f"      {r['note']}")
        print()
    return 0


def cmd_add(args) -> int:
    rows = load()
    sid = share_id({"url": args.url}) if args.url else args.id
    if not sid:
        print("必须给 --url 或 --id")
        return 1
    if any(share_id(r) == sid for r in rows):
        print(f"已存在：{sid}，跳过")
        return 0
    item = {
        "id": sid,
        "title": args.title or "",
        "item": args.item or "",
        "kind": "quark",
        "url": args.url or f"https://pan.quark.cn/s/{sid}",
        "short": args.short or "",
        "source": args.source or "",
        "published": args.published or "",
        "status": "unknown",
        "saved": args.saved or "",
        "added": dt.date.today().isoformat(),
        "note": args.note or "",
    }
    rows.append(item)
    save(rows)
    render(rows)
    print(f"已记录：{item['title']} / {item['item']} → {sid}")
    print(f"台账已更新：{MD}")
    return 0


def cmd_rm(args) -> int:
    rows = load()
    key = args.id
    keep = [r for r in rows if share_id(r) != key and r.get("title") != key and r.get("item") != key]
    if len(keep) == len(rows):
        print(f"没找到匹配 {key} 的记录")
        return 1
    save(keep)
    render(keep)
    print(f"已删除 {len(rows) - len(keep)} 条，剩余 {len(keep)} 条")
    return 0


def cmd_set(args) -> int:
    rows = load()
    hit = 0
    for r in rows:
        if share_id(r) == args.id or r.get("title") == args.id:
            r[args.field] = args.value
            hit += 1
    if not hit:
        print(f"没找到 {args.id}")
        return 1
    save(rows)
    render(rows)
    print(f"已更新 {hit} 条：{args.field} = {args.value}")
    return 0


def cmd_render(args) -> int:
    rows = load()
    render(rows)
    print(f"已渲染 {MD}（{len(rows)} 条）")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="网盘资源台账")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="新增一条记录")
    a.add_argument("--title", required=True, help="片名")
    a.add_argument("--item", help="具体内容，如「第5期」「全集」")
    a.add_argument("--url", help="分享链接")
    a.add_argument("--id", help="分享 id（不给 url 时用）")
    a.add_argument("--short", help="微博短链等")
    a.add_argument("--source", help="来源，如「微博 @某某」")
    a.add_argument("--published", help="资源发布时间")
    a.add_argument("--saved", help="已转存位置")
    a.add_argument("--note", help="备注")
    a.set_defaults(func=cmd_add)

    b = sub.add_parser("list", help="列出全部")
    b.set_defaults(func=cmd_list)

    c = sub.add_parser("check", help="核验链接有效性")
    c.add_argument("--id", help="只核验某一条（id 或片名）")
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("render", help="重渲染 resources.md")
    d.set_defaults(func=cmd_render)

    e = sub.add_parser("rm", help="删除一条记录")
    e.add_argument("--id", required=True, help="分享 id / 片名 / 内容任一匹配即可")
    e.set_defaults(func=cmd_rm)

    f = sub.add_parser("set", help="改某条记录的字段")
    f.add_argument("--id", required=True, help="分享 id 或片名")
    f.add_argument("--field", required=True, help="字段名，如 saved / note / status")
    f.add_argument("--value", required=True, help="新值")
    f.set_defaults(func=cmd_set)

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
