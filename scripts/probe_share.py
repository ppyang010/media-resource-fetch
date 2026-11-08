#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克分享内容探针：不转存，只列目录，用来看某个分享里有什么、更新到第几期。

端点取自插件 app/plugins/cloudsubscribe/drive/quark/share.py：
  POST https://drive-h.quark.cn/1/clouddrive/share/sharepage/token
  GET  https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail

用法：
  python probe_share.py b5ba3729fd0a 6fc850c24135 ...
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://drive-h.quark.cn/1/clouddrive"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _req(url: str, data: dict | None = None, method: str = "GET") -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://pan.quark.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    if body:
        req.add_header("Content-Type", "application/json")
    with OPENER.open(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")


def list_share(share_id: str, passcode: str = "", depth: int = 4) -> None:
    try:
        tok = _req(
            f"{BASE}/share/sharepage/token",
            {"pwd_id": share_id, "passcode": passcode,
             "support_visit_limit_private_share": True},
            method="POST",
        )
    except urllib.error.HTTPError as e:
        print(f"[{share_id}] token HTTP {e.code} → 分享已失效")
        return
    except Exception as e:
        print(f"[{share_id}] token 请求失败：{e}")
        return

    stoken = (tok.get("data") or {}).get("stoken")
    if not stoken:
        code = tok.get("code")
        msg = tok.get("message") or tok.get("msg") or ""
        print(f"[{share_id}] 无 stoken（code={code} {msg}）→ 分享可能已失效或需提取码")
        return

    def _walk(fid: str, level: int) -> None:
        q = urllib.parse.urlencode({
            "pwd_id": share_id, "stoken": stoken, "pdir_fid": fid,
            "force": "0", "_page": 1, "_size": 200,
            "_fetch_banner": "1", "_fetch_share": "1", "_fetch_total": "1",
            "_sort": "file_type:asc,file_name:asc",
        })
        try:
            detail = _req(f"{BASE}/share/sharepage/detail?{q}")
        except Exception as e:
            print(f"    detail 请求失败：{e}")
            return
        data = detail.get("data") or {}
        files = data.get("list") or []
        indent = "    " * level
        if level == 1:
            share = data.get("share") or {}
            print(f"[{share_id}] {share.get('title') or ''} | 共 {data.get('total') or len(files)} 项")
        for f in files[:200]:
            size = int(f.get("size") or 0)
            size_s = f"{size/1024/1024/1024:.1f}G" if size > 1024**3 else f"{size/1024/1024:.0f}M"
            kind = "DIR " if f.get("dir") else "FILE"
            print(f"{indent}{kind} {str(f.get('file_name'))[:52]:<54} {size_s}")
        if level < depth:
            for f in files:
                if f.get("dir"):
                    _walk(str(f.get("fid")), level + 1)

    _walk("0", 1)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    for arg in argv[1:]:
        sid = arg.rstrip("/").split("/")[-1].replace("s/", "")
        list_share(sid)
        print()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv))
