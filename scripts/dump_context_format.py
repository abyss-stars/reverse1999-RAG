"""把 LightRAG `only_need_context` 的真实返回格式抓下来，供薄服务层写"上下文裁剪"用。

薄服务层要做「检索 → 按版本过滤 → 生成」，过滤那一步必须精确知道上下文长什么样：
KG 段与 Document Chunks 段各自的形状、引用序号怎么标、Reference List 怎么排。
猜格式一定会踩坑，所以先把它 dump 出来。

用法：
    python scripts/dump_context_format.py            # 默认 mix（同时有 KG 与 chunks）
    python scripts/dump_context_format.py --mode naive
"""

from __future__ import annotations

import argparse
import json
import pathlib
import ssl
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "ref" / "context-sample.txt"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:9621")
    ap.add_argument("--mode", default="mix")
    ap.add_argument("--query", default="「这是我的箱子，请还给我。」这句话是谁说的？")
    args = ap.parse_args()

    body = {
        "query": args.query,
        "mode": args.mode,
        "top_k": 60,
        "chunk_top_k": 30,
        "max_entity_tokens": 12000,
        "max_relation_tokens": 22000,
        "max_total_tokens": 90000,
        "enable_rerank": True,
        "only_need_context": True,
        "include_references": True,
        "include_chunk_content": True,
    }
    req = urllib.request.Request(
        f"{args.base}/query",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300, context=CTX) as resp:
        data = json.loads(resp.read())

    ctx = data.get("response") or ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(ctx, encoding="utf-8")

    refs = data.get("references") or []
    print(f"上下文长度 : {len(ctx)} 字符  → {OUT.relative_to(ROOT)}")
    print(f"引用条数   : {len(refs)}")
    print("\n=== 段标题（以 '#' 开头的行）===")
    for line in ctx.splitlines():
        if line.startswith("#"):
            print(f"  {line[:100]}")
    print("\n=== 前 40 行 ===")
    for line in ctx.splitlines()[:40]:
        print(f"  {line[:150]}")
    print("\n=== 引用列表结构（前 3 条）===")
    for r in refs[:3]:
        content = r.get("content")
        print(
            f"  id={r.get('reference_id')!r} file={r.get('file_path')!r} "
            f"content={'list(%d)' % len(content) if isinstance(content, list) else content!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
