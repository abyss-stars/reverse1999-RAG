#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preset_matrix.py — 预设参数标定矩阵

对每个预设跑一组代表性问题，只用 `only_need_context=true` 取上下文
（不调 LLM 生成），因此**便宜且直击问题本质**：回答的质量上限由检索覆盖决定。

每次改动 query_planner.PRESETS 之后都应该重跑一次，把新数字写回 docs/检索调参.md。

用法:
    python scripts/preset_matrix.py                # 完整 5x5 矩阵
    python scripts/preset_matrix.py --only sweep   # 只跑某个预设
    python scripts/preset_matrix.py --json         # 机器可读输出
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline" / "lib"))
from query_planner import PRESETS, PRESET_ORDER, plan  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 每个预设的代表性问题（即前端上用户会点这个预设来问的那类问题）
QUESTIONS = {
    "pinpoint": "「这是我的箱子，请还给我」这句话是谁说的",
    "lookup": "阿尔卡纳是什么",
    "chain": "维尔汀和 APPLe 是什么关系",
    "sweep": "游戏剧情从2.0到3.0之间发生了哪些重大事件",
    "quick": "苏芙比是谁",
}

# 交叉验证用的「宽泛问题」：用来看不同预设在同一难题上的覆盖/延迟差异
CROSS_QUESTION = "游戏剧情从2.0到3.0之间发生了哪些重大事件"


def api_base() -> str:
    env = {}
    ep = ROOT / ".env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return f"http://localhost:{env.get('PORT', '9621')}"


def load_chapters() -> dict:
    idx = json.loads((ROOT / "state" / "chapter_index.json").read_text(encoding="utf-8"))
    return {c["filename"]: c for c in idx["chapters"]}


def run_query(base: str, question: str, params: dict) -> dict:
    body = {
        "query": question,
        "only_need_context": True,      # 不调生成，只测检索
        "include_references": True,
        "include_chunk_content": True,
    }
    body.update(params)
    req = urllib.request.Request(
        base + "/query", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    dt = time.time() - t0

    refs = data.get("references") or []
    names, nchunk, chars = set(), 0, 0
    for ref in refs:
        fp = (ref.get("file_path") or "").replace("\\", "/")
        names.add(fp.split("/")[-1])
        content = ref.get("content") or []
        nchunk += len(content)
        chars += sum(len(c) for c in content)
    return {"seconds": round(dt, 1), "refs": len(refs), "chunks": nchunk,
            "chars": chars, "files": names}


def main() -> int:
    ap = argparse.ArgumentParser(description="预设参数标定矩阵")
    ap.add_argument("--only", default="", help="只跑指定预设")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    base = api_base()
    chapters = load_chapters()
    wanted = [args.only] if args.only else PRESET_ORDER

    results: dict[str, dict] = {}
    for qname in wanted:
        q = QUESTIONS[qname]
        row = {}
        for pname in PRESET_ORDER:
            p = plan(pname)
            try:
                r = run_query(base, q, p.params())
            except Exception as exc:  # noqa: BLE001
                row[pname] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            orders = sorted({chapters[f]["order"] for f in r["files"] if f in chapters})
            r["orders"] = orders
            r["n_orders"] = len(orders)
            row[pname] = r
        results[qname] = row

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=list))
        return 0

    # ---- 每问一表：同一问题下横向对比各预设
    for qname in wanted:
        print(f"\n{'=' * 104}")
        print(f"问题类型 [{qname}]  「{QUESTIONS[qname]}」")
        print(f"{'=' * 104}")
        print(f"{'预设':<10}{'mode':<7}{'耗时':>7}{'refs':>6}{'chunks':>8}"
              f"{'字符':>9}{'命中章节':>9}   命中的阅读顺序(前 20)")
        print("-" * 104)
        for pname, r in results[qname].items():
            if "error" in r:
                print(f"{pname:<10}ERROR {r['error']}")
                continue
            o = ",".join(str(x) for x in r["orders"][:20])
            print(f"{pname:<10}{PRESETS[pname]['mode']:<7}{r['seconds']:>6.1f}s"
                  f"{r['refs']:>6}{r['chunks']:>8}{r['chars']:>9}{r['n_orders']:>9}   {o}")

    # ---- 汇总：每个预设「自己最擅长的那类问题」上的表现
    print(f"\n\n{'=' * 104}")
    print("汇总：每个预设在其代表性问题上的表现（这对应用户在前端选它的预期）")
    print(f"{'=' * 104}")
    print(f"{'预设':<10}{'耗时':>7}{'refs':>6}{'chunks':>8}{'字符':>9}"
          f"{'命中章节':>9}   {'检索档':<8}{'花费档'}")
    print("-" * 104)
    for qname in wanted:
        r = results[qname].get(qname, {})
        if "error" in r or not r:
            print(f"{qname:<10}  (无数据)")
            continue
        p = PRESETS[qname]
        print(f"{qname:<10}{r['seconds']:>6.1f}s{r['refs']:>6}{r['chunks']:>8}"
              f"{r['chars']:>9}{r['n_orders']:>9}   {p['latency']:<8}{p['cost']}")

    # ---- 交叉：同一个宽泛问题在各预设下的差异
    if "sweep" in results and not args.only:
        print(f"\n\n{'=' * 104}")
        print(f"交叉验证：同一个宽泛问题「{CROSS_QUESTION}」在各预设下")
        print(f"{'=' * 104}")
        print(f"{'预设':<10}{'耗时':>7}{'refs':>6}{'chunks':>8}{'字符':>9}{'命中章节':>9}")
        print("-" * 104)
        for pname, r in results["sweep"].items():
            if "error" in r:
                continue
            print(f"{pname:<10}{r['seconds']:>6.1f}s{r['refs']:>6}{r['chunks']:>8}"
                  f"{r['chars']:>9}{r['n_orders']:>9}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
