#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ingest.py — 把 data/inputs/ 里的章节灌入 LightRAG，并维护 state/index_manifest.json

用法:
    python pipeline/ingest.py --status              查看服务与索引进度
    python pipeline/ingest.py --scan                触发扫描并入队（首次全量 / 日常增量）
    python pipeline/ingest.py --watch               持续盯进度直到管线空闲
    python pipeline/ingest.py --backfill            把 doc_id / status / chunks 回填 manifest
    python pipeline/ingest.py --ask "维尔汀是谁"     冒烟测试一次问答
    python pipeline/ingest.py --check-parser        验证 md:native-P 是否真的生效

说明:
    * 灌入统一走 /documents/scan：LightRAG 会把 INPUT_DIR 顶层的文件与 doc_status 比对，
      新增的入队、已 PROCESSED 的归档。
    * 更新某一章必须先删除该文档再重新扫描，否则同名/同内容会被判重
      （见 update_index.py）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.lightrag_client import LightRAGClient, LightRAGError  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "state" / "index_manifest.json"
INPUTS = ROOT / "data" / "inputs"

STATUS_ORDER = ["PENDING", "PARSING", "ANALYZING", "PROCESSING", "PROCESSED", "FAILED"]


def client_from_env() -> LightRAGClient:
    """从 .env 读 HOST/PORT/LIGHTRAG_API_KEY（容器内 0.0.0.0 → 本机 localhost）。"""
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    port = env.get("PORT", "9621")
    return LightRAGClient(
        base_url=f"http://localhost:{port}",
        api_key=env.get("LIGHTRAG_API_KEY", ""),
        timeout=300,
    )


def load_manifest() -> dict:
    if not MANIFEST.exists():
        print("[!] 找不到 state/index_manifest.json")
        print("    请先运行: python pipeline/chapter_index.py && python pipeline/build_inputs.py")
        sys.exit(1)
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(m: dict) -> None:
    m["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_counts(c: dict) -> str:
    if not c:
        return "(无)"
    order = [k for k in STATUS_ORDER if k in c] + [k for k in c if k not in STATUS_ORDER]
    return "  ".join(f"{k}={c[k]}" for k in order)


# ------------------------------------------------------------------ 命令
def cmd_status(cli: LightRAGClient) -> int:
    try:
        h = cli.health()
    except LightRAGError as e:
        print(f"[x] {e}")
        return 1

    print("=== 服务 ===")
    print(f"  core_version : {h.get('core_version')}")
    print(f"  api_version  : {h.get('api_version')}")
    print(f"  workspace    : {h.get('workspace')}")
    print(f"  pipeline_busy: {h.get('pipeline_busy')}")

    ps = cli.pipeline_status()
    print("\n=== 管线 ===")
    print(f"  busy          : {ps.get('busy')}")
    print(f"  job_name      : {ps.get('job_name')}")
    print(f"  latest_message: {str(ps.get('latest_message'))[:150]}")

    sc = cli.status_counts()
    print("\n=== 文档状态 ===")
    print(f"  {fmt_counts(sc.get('status_counts', sc))}")

    # 本地清单统计
    if MANIFEST.exists():
        m = load_manifest()
        docs = m["docs"]
        done = sum(1 for d in docs.values() if d.get("status") == "PROCESSED")
        print(f"\n=== 本地清单 ===")
        print(f"  章节总数: {len(docs)}   已索引: {done}")
    return 0


def cmd_scan(cli: LightRAGClient) -> int:
    n = len(list(INPUTS.glob("*.md")))
    n_arch = len([p for p in (INPUTS / "__parsed__").glob("*.md")]) if (INPUTS / "__parsed__").exists() else 0
    print(f"INPUT_DIR 顶层待处理章节: {n}")
    if n == 0:
        print(f"\n[!] INPUT_DIR 顶层没有 .md —— 扫描会得到 0 discovered。")
        print(f"    已归档(处理过的)章节: {n_arch} 个，它们在 data/inputs/__parsed__/ 下。")
        print(f"    LightRAG 处理完一份文件后会把源文件移进 __parsed__/，")
        print(f"    所以要重新灌必须先重新铺入:")
        print(f"      python pipeline/build_inputs.py --categories mainline")
        return 1

    try:
        r = cli.scan()
    except LightRAGError as e:
        print(f"[x] 触发扫描失败: {e}")
        return 1

    status = r.get("status")
    track = r.get("track_id")
    print(f"  scan status: {status}   track_id: {track}")

    if status and "skipped" in str(status):
        print(f"\n[!] 扫描被拒绝: {status}")
        print("    常见原因: 管线正忙 / 已有扫描在跑 / 有未确认的手动重试排队")
        print("    处理: 等管线空闲, 或 POST /documents/reprocess_failed")
        return 1

    if track:
        print("  等待扫描分类阶段完成 ...")
        st = cli.wait_for_scan(track)
        c = (st.get("counts") or {})
        print(f"  扫描结果: {st.get('status')}  discovered={c.get('discovered')}")
        print(f"  {st.get('message')}")

    print("\n[ok] 已入队。用下面命令盯进度:")
    print("     python pipeline/ingest.py --watch")
    return 0


def cmd_watch(cli: LightRAGClient, poll: float = 5.0) -> int:
    """盯进度直到全部文档进入终态。

    完成判据必须同时满足两条, 只看 busy 会在长批次里误判:
      1. 管线不活跃(busy/scanning/pending_enqueues 全无)
      2. 没有任何文档处于非终态(pending/parsing/analyzing/processing)
    因为批次之间会有短暂空档, 那时 busy 会瞬间变 False。
    """
    NON_TERMINAL = {"pending", "parsing", "analyzing", "processing"}
    print("盯进度中 (Ctrl+C 退出) ...\n")
    t0 = time.time()
    last = ""
    try:
        while True:
            ps = cli.pipeline_status()
            counts = cli.status_counts().get("status_counts", {}) or {}
            msg = str(ps.get("latest_message") or "")[:110]
            phase = "scanning" if (ps.get("scanning") or ps.get("scanning_exclusive")) else ""
            line = f"[{int(time.time()-t0):>6}s] {fmt_counts(counts)} {phase} | {msg}"
            if line != last:
                print(line, flush=True)
                last = line

            still_running = sum(
                v for k, v in counts.items() if str(k).lower() in NON_TERMINAL
            )
            if not cli._is_active(ps) and still_running == 0:
                print("\n[ok] 全部文档已进入终态, 管线空闲")
                break
            time.sleep(poll)
    except KeyboardInterrupt:
        print("\n(用户中断)")
    return 0


def cmd_backfill(cli: LightRAGClient) -> int:
    """把 LightRAG 的 doc_status 回填进本地 manifest。"""
    m = load_manifest()
    docs = m["docs"]

    # 分页拉全部文档
    all_docs: list[dict] = []
    page = 1
    while True:
        r = cli.documents_paginated(page=page, page_size=200)
        batch = r.get("documents") or []
        all_docs.extend(batch)
        pg = r.get("pagination") or {}
        total = pg.get("total_count") or pg.get("total") or len(all_docs)
        if not batch or len(all_docs) >= total:
            break
        page += 1

    print(f"LightRAG 返回 {len(all_docs)} 个文档")

    # 以 file_path 的 basename 对齐本地清单
    by_name: dict[str, dict] = {}
    for d in all_docs:
        fp = d.get("file_path") or ""
        name = Path(fp).name
        if name:
            by_name[name] = d

    updated = missing = 0
    for name, rec in docs.items():
        d = by_name.get(name)
        if not d:
            missing += 1
            continue
        rec["lightrag_doc_id"] = d.get("id") or d.get("doc_id")
        # API 返回小写状态(processed/failed/...), 统一成大写便于比较与展示
        st = d.get("status")
        rec["status"] = st.upper() if isinstance(st, str) else st
        rec["chunks_count"] = d.get("chunks_count")
        if rec["status"] == "PROCESSED":
            rec["indexed_at"] = d.get("updated_at") or datetime.now(timezone.utc).isoformat()
        updated += 1

    save_manifest(m)
    print(f"  已回填 {updated} 章, 未在 LightRAG 找到 {missing} 章")

    done = sum(1 for d in docs.values() if d.get("status") == "PROCESSED")
    failed = [n for n, d in docs.items() if d.get("status") == "FAILED"]
    print(f"  PROCESSED: {done}/{len(docs)}")
    if failed:
        print(f"  [!] FAILED {len(failed)} 章:")
        for n in failed[:10]:
            print(f"      {n}")
    return 0


def cmd_ask(cli: LightRAGClient, q: str) -> int:
    print(f"问: {q}\n")
    t0 = time.time()
    try:
        r = cli.query(q, mode="mix", include_references=True,
                      include_chunk_content=False)
    except LightRAGError as e:
        print(f"[x] {e}")
        return 1
    print(f"答 ({time.time()-t0:.1f}s):\n{r.get('response')}\n")
    refs = r.get("references") or []
    if refs:
        print(f"引用 {len(refs)} 处:")
        for ref in refs[:8]:
            print(f"  [{ref.get('reference_id')}] {ref.get('file_path')}")
    return 0


def cmd_check_parser(cli: LightRAGClient) -> int:
    """确认 .md 实际路由到哪个引擎 —— 验证 P 分块是否真的生效。"""
    try:
        r = cli.supported_file_types()
    except LightRAGError as e:
        print(f"[x] {e}")
        return 1
    print("=== 实际生效的后缀 → 引擎映射 ===")
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2500])
    print("\n判读: 若 md 映射到 native, 且 .env 里 LIGHTRAG_PARSER=md:native-P,")
    print("      则 P 分块生效; 若落到 legacy, 说明路由没匹配上, P 会降级成 R。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="1999RAG 灌库与巡检", 
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="查看服务与索引进度")
    g.add_argument("--scan", action="store_true", help="触发扫描并入队")
    g.add_argument("--watch", action="store_true", help="盯进度直到空闲")
    g.add_argument("--backfill", action="store_true", help="回填 manifest")
    g.add_argument("--check-parser", action="store_true", help="验证分块路由")
    g.add_argument("--ask", metavar="QUESTION", help="冒烟测试一次问答")
    args = ap.parse_args()

    cli = client_from_env()

    if args.status:
        return cmd_status(cli)
    if args.scan:
        return cmd_scan(cli)
    if args.watch:
        return cmd_watch(cli)
    if args.backfill:
        return cmd_backfill(cli)
    if args.check_parser:
        return cmd_check_parser(cli)
    if args.ask:
        return cmd_ask(cli, args.ask)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
