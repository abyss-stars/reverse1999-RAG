#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
smoke_test.py — 剧情 RAG 验收回归

四类问题各测一个能力维度：

  1. 单点事实    —— 检索能否落到正确章节
  2. 跨章汇总    —— 能否触发图的 global / 多跳检索
  3. 人物关系    —— 能否用图回答关系类问题
  4. 说话人归属  —— 对话体切块有没有把"谁说的"切散

判读重点不在答案文采，而在：
  * references 里的 file_path 是否是相关章节
  * 第 4 题必须答出正确的说话人
  * 答案里是否出现凭空捏造的人名/设定（幻觉）

用法:
    python scripts/smoke_test.py                    # 跑全部
    python scripts/smoke_test.py --only 4           # 只跑第 4 题
    python scripts/smoke_test.py --mode naive       # 换检索模式
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from lib.lightrag_client import LightRAGClient, LightRAGError  # noqa: E402

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

CASES = [
    {
        "id": 1,
        "kind": "单点事实",
        "q": "维尔汀在序章里对十四行诗说了什么？",
        "expect": "引用应落在 101-在我们的时代里.md",
    },
    {
        "id": 2,
        "kind": "跨章汇总",
        "q": "苏芙比这个角色在主线里有哪些经历？",
        "expect": "需要跨多个剧情单元汇总，引用应涉及 101 章内多个位置",
    },
    {
        "id": 3,
        "kind": "人物关系",
        "q": "维尔汀和APPLe是什么关系？",
        "expect": "应能说明是同伴/同行关系",
    },
    {
        "id": 4,
        "kind": "说话人归属",
        "q": "「这是我的箱子，请还给我。」这句话是谁说的？",
        "expect": "必须答出「维尔汀」",
    },
    {
        "id": 5,
        "kind": "跨主线·人物",
        "q": "阿尔卡纳是谁？她和维尔汀之间发生过什么？",
        "expect": "应覆盖 102 章首次登场及后续章节的多次交锋",
    },
    {
        "id": 6,
        "kind": "跨主线·世界观",
        "q": "「暴雨」到底是什么？它对世界有什么影响？",
        "expect": "应跨多章汇总设定，而非只答某一章",
    },
    {
        "id": 7,
        "kind": "跨主线·主线伏笔",
        "q": "维尔汀的身世和「实验体」身份是怎么被揭示的？",
        "expect": "应串联 102 章的三个问题与后续章节的相关线索",
    },
    {
        "id": 8,
        "kind": "角色剧情分类",
        "q": "角色剧情《打虎记》讲了什么？",
        "expect": "应能检索到 character 分类的该章内容",
    },
    {
        "id": 9,
        "kind": "轶事分类",
        "q": "轶事《塞梅尔维斯》讲了什么？",
        "expect": "应能检索到 anecdote 分类的该章内容",
    },
    {
        "id": 10,
        "kind": "活动分类",
        "q": "活动《飞驰！明日之城》的剧情梗概是什么？",
        "expect": "应能检索到 activity 分类的该章内容",
    },
]


def client_from_env() -> LightRAGClient:
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return LightRAGClient(
        base_url=f"http://localhost:{env.get('PORT', '9621')}",
        api_key=env.get("LIGHTRAG_API_KEY", ""),
        timeout=600,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="剧情 RAG 验收回归")
    ap.add_argument("--only", type=int, help="只跑指定题号")
    ap.add_argument("--mode", default="mix",
                    help="检索模式: mix / hybrid / local / global / naive (默认 mix)")
    ap.add_argument("--show-refs", action="store_true", default=True,
                    help="打印引用来源(默认开)")
    args = ap.parse_args()

    cli = client_from_env()

    try:
        h = cli.health()
        sc = cli.status_counts().get("status_counts", {})
    except LightRAGError as e:
        print(f"[x] 服务不可用: {e}")
        return 1

    print(f"服务: core={h.get('core_version')}  文档: {sc}")
    print(f"检索模式: {args.mode}")
    print("=" * 72)

    cases = [c for c in CASES if args.only is None or c["id"] == args.only]
    ok = 0

    for c in cases:
        print(f"\n【第 {c['id']} 题 · {c['kind']}】")
        print(f"问: {c['q']}")
        print(f"期望: {c['expect']}")
        t0 = time.time()
        try:
            r = cli.query(c["q"], mode=args.mode, include_references=True,
                          include_chunk_content=False, enable_rerank=True)
        except LightRAGError as e:
            print(f"  [x] 查询失败: {e}")
            continue
        dt = time.time() - t0

        ans = (r.get("response") or "").strip()
        print(f"\n答 ({dt:.1f}s):")
        for line in ans.splitlines():
            print(f"  {line}")

        refs = r.get("references") or []
        if refs and args.show_refs:
            print(f"\n引用 {len(refs)} 处:")
            seen = set()
            for ref in refs:
                fp = ref.get("file_path") or "?"
                if fp in seen:
                    continue
                seen.add(fp)
                print(f"  - {fp}")
                if len(seen) >= 8:
                    break

        # 第 4 题的硬性判据
        if c["id"] == 4:
            if "维尔汀" in ans:
                print("\n  [PASS] 答出了说话人「维尔汀」")
                ok += 1
            else:
                print("\n  [FAIL] 未答出「维尔汀」——对话体切块可能把说话人切散了")
        elif ans:
            ok += 1
        print("-" * 72)

    print(f"\n通过 {ok}/{len(cases)}")
    return 0 if ok == len(cases) else 2


if __name__ == "__main__":
    raise SystemExit(main())
