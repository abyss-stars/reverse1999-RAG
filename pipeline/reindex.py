#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
reindex.py — 强制重灌指定章节（清洗/渲染逻辑变更后刷新索引正文）

场景: 改了 build_inputs.py 的头部渲染（例如往章节头加一行「游戏版本 X.Y」）后，
      data/cleaned/ 正文变了，但 LightRAG 里仍是旧文本。扫描不会重灌已 PROCESSED
      的文档（会被判为 already processed），所以必须先删后传。

用法:
    python pipeline/reindex.py --chapters 109,111,112            # 预览（默认 dry-run）
    python pipeline/reindex.py --chapters 109,111,112 --apply    # 执行
    python pipeline/reindex.py --from-plan state/_reindex_plan.json --apply
    python pipeline/reindex.py --category anecdote --apply       # 整类重灌

注意: 删除时固定 delete_llm_cache=False —— 保住花过钱的抽取缓存，
      只有真正变了的 chunk 会重新抽取。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "state" / "index_manifest.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_manifest() -> dict:
    if not MANIFEST.exists():
        print(f"[x] 缺少 {MANIFEST}")
        raise SystemExit(1)
    return json.loads(MANIFEST.read_text(encoding="utf-8")).get("docs", {})


def client():
    sys.path.insert(0, str(ROOT / "pipeline" / "lib"))
    from lightrag_client import LightRAGClient  # noqa: E402

    env = {}
    ep = ROOT / ".env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return LightRAGClient(base_url=f"http://localhost:{env.get('PORT', '9621')}",
                          api_key=env.get("LIGHTRAG_API_KEY", ""), timeout=600)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="强制重灌指定章节", formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chapters", help="章号列表, 逗号分隔 (如 109,111,112)")
    g.add_argument("--from-plan", help="从 JSON 计划文件读取 chapter_no 列表")
    g.add_argument("--category", help="按分类整类重灌 (mainline/activity/character/anecdote)")
    ap.add_argument("--apply", action="store_true", help="真正执行(缺省仅预览)")
    return ap.parse_args()


def resolve_targets(args, docs: dict) -> list[dict]:
    if args.from_plan:
        plan = json.loads((ROOT / args.from_plan).read_text(encoding="utf-8"))
        nos = [str(r["chapter_no"]) for r in plan]
    elif args.category:
        nos = [rec["chapter_no"] for rec in docs.values()
               if rec.get("category") == args.category]
    else:
        nos = [s.strip() for s in args.chapters.split(",") if s.strip()]

    out = []
    for no in nos:
        rec = next((r for r in docs.values() if str(r.get("chapter_no")) == no), None)
        if not rec:
            print(f"  [warn] 清单里找不到章号 {no}，跳过")
            continue
        out.append({"chapter_no": no, "filename": rec.get("filename") or "",
                    "title": rec.get("title"), "doc_id": rec.get("lightrag_doc_id")})
    return out


def main() -> int:
    args = parse_args()
    docs = load_manifest()
    targets = resolve_targets(args, docs)
    if not targets:
        print("[x] 没有可重灌的章节")
        return 1

    with_doc = [t for t in targets if t["doc_id"]]
    nos = sorted(t["chapter_no"] for t in targets)

    print(f"待重灌 {len(targets)} 章（其中已有索引 {len(with_doc)} 章）")
    for t in targets[:10]:
        print(f"  {t['chapter_no']:<8} {t['title']}")
    if len(targets) > 10:
        print(f"  ... 另有 {len(targets) - 10} 章")

    if not args.apply:
        print("\n[dry-run] 未做任何改动。加 --apply 执行。")
        print(f"  将执行: 删除 {len(with_doc)} 个文档 → 铺入 {len(targets)} 章 → scan → backfill")
        return 0

    cli = client()

    if with_doc:
        print(f"\n-> 删除 {len(with_doc)} 个已索引文档（保留抽取缓存）")
        ids = [t["doc_id"] for t in with_doc]
        for i in range(0, len(ids), 20):
            batch = ids[i:i + 20]
            try:
                cli.delete_document(batch, delete_file=False, delete_llm_cache=False)
                print(f"   已提交 {i + len(batch)}/{len(ids)}")
            except Exception as exc:  # noqa: BLE001
                print(f"   [warn] 删除失败: {exc}")
        print("-> 等待删除完成 ...")
        cli.wait_for_idle(timeout=3600)
    else:
        print("\n-> 无需删除")

    print(f"\n-> 铺入 {len(targets)} 章到 INPUT_DIR")
    subprocess.run([sys.executable, str(ROOT / "pipeline" / "build_inputs.py"),
                    "--categories", "all", "--chapters", ",".join(nos)], check=True)

    print("-> 触发扫描")
    r = cli.scan()
    print(f"   {r.get('status')}  track={r.get('track_id')}")

    print("-> 等待管线跑完（章节多时会较久）...")
    cli.wait_for_idle(timeout=14400,
                      on_tick=lambda st, t: print(f"   [{int(t):>6}s] "
                                                  f"{str(st.get('latest_message', ''))[:100]}"))

    print("\n-> 回填清单")
    subprocess.run([sys.executable, str(ROOT / "pipeline" / "ingest.py"), "--backfill"],
                   check=True)

    print(f"\n[ok] 重灌完成，共 {len(targets)} 章")
    print("     提交清单: git add state/ && git commit -m "
          f"'index: reindex {len(targets)} chapters'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
