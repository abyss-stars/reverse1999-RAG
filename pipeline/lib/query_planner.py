#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
query_planner.py — 检索参数预设表

定位
----
**预设由用户在前端选择，本模块不做问题分类、不做热词匹配。**
它只负责两件事：

1. 给每个预设一组**实测标定过**的检索参数；
2. 给前端提供展示元数据（名称、说明、适合什么问题、延迟档、花费档）。

为什么要预设
------------
LightRAG 的 `/query` 有 20 个查询期参数，但实测下来只有 `mode` 与几个 token
预算是真杠杆：

- **瓶颈是 `max_total_tokens`，不是 `chunk_top_k`。**
  同一个宽泛问题：默认预算只覆盖 10 章；预算 ×4 覆盖 26 章；
  `naive` + 140k 覆盖 49 章。而单独把 `chunk_top_k` 从 120 调到 200，
  覆盖反而从 38 章掉到 19 章 —— 候选多了但预算不变，rerank 只是换一批进来。
- **`naive` 不只是覆盖更广，它还更快。** `mix` / `local` 在检索前要先花一次
  LLM 调用抽关键词，而 `naive` 不用。实测同样是 pinpoint 类问题：
  `naive` 4.6s 答对，`mix` 8.1s 答对；同样是宽泛问题：`naive` 3.3s 覆盖 49 章，
  `mix` 6.4s 只覆盖 21 章。**所以只有真正需要图关系时才用 `mix`/`local`。**

五个预设
--------
| 预设 | 名称 | 适合 |
|---|---|---|
| `pinpoint` | 精确定位 | 某句原话是谁说的、某个具体事实 |
| `lookup` | 专名检索 | 某个人物/组织/术语是什么 |
| `chain` | 关系链 | 谁和谁什么关系、为什么会这样、时间线 |
| `sweep` | 广域扫掠 | 有哪些、完整经历、某版本区间发生了什么 |
| `quick` | 快速应答 | 连续追问、流式输出等对延迟敏感的场景 |

标定方法
--------
`scripts/preset_matrix.py` 用 `only_need_context=true` 跑预设矩阵（只取上下文、
不调生成，因此便宜），再对高风险项（大预算）单独跑一次真实生成确认上下文塞得进模型。
**改动参数后请重跑该脚本。**

用法
----
    from query_planner import plan, for_ui

    p = plan("sweep")              # 用户在前端选了「广域扫掠」
    p.params()                     # 可直接合并进 /query 请求体

    for item in for_ui():          # 前端渲染选项列表
        ...
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------- 预设定义
# 字段分三组：
#   * 展示元数据  label / summary / when / latency / cost   —— 给前端用
#   * 检索参数    mode / top_k / chunk_top_k / max_*_tokens —— 直接进 /query
#   * extra       该预设专属的额外请求字段（如 enable_rerank）
#
# latency / cost 都是**实测得出的相对档位**，不是拍脑袋：
#   latency = 检索耗时档（naive < local < mix）
#   cost    = 上下文规模档，同时决定 API 花费与生成耗时
PRESETS: dict[str, dict] = {
    "pinpoint": {
        "label": "精确定位",
        "summary": "某句话是谁说的，或某个具体事实",
        "when": "问题指向明确，答案就在一两段对话里。例：「『这是我的箱子』是谁说的」",
        "latency": "低",
        "cost": "低",
        "mode": "naive",
        "top_k": 40,
        "chunk_top_k": 40,
        "max_entity_tokens": 2000,
        "max_relation_tokens": 2000,
        "max_total_tokens": 32000,
        "why": "原设计用 `mix`，实测**答对率相同但慢 1.5–1.8×**（4.6s vs 8.1s），"
               "且覆盖不增反减（13 章 vs 12 章）。引语句本身辨识度极高，"
               "纯向量检索就能命中，图检索在这里是净开销。"
               "候选给到 40 是为了让 rerank 有足够素材排序。",
    },
    "lookup": {
        "label": "专名检索",
        "summary": "某个人物、组织或术语是什么",
        "when": "问的是「X 是什么 / 是谁 / 什么意思」，目标是拿到该条目的定义与背景",
        "latency": "中",
        "cost": "中",
        "mode": "local",
        "top_k": 60,
        "chunk_top_k": 25,
        "max_entity_tokens": 9000,
        "max_relation_tokens": 5000,
        "max_total_tokens": 45000,
        "why": "五个预设里唯一用实体锚定检索的：`local` 会取该实体的**累积描述 + 关系**，"
               "是压缩过的定义型信息，正是「X 是什么」要的。"
               "代价是 chunk 数少于 `naive`（19 vs 25），换来的信息更浓缩。"
               "实测把 top_k 从 40 提到 60、chunk_top_k 从 12 提到 25 后，"
               "覆盖 12→19 chunk 且耗时反而从 4.7s 降到 3.5s。",
    },
    "chain": {
        "label": "关系链",
        "summary": "谁和谁什么关系、为什么会这样、事情的先后顺序",
        "when": "需要跨越多处线索串联，或要理清因果与时间线。例：「A 和 B 是什么关系」",
        "latency": "中高",
        "cost": "高",
        "mode": "mix",
        "top_k": 60,
        "chunk_top_k": 30,
        "max_entity_tokens": 12000,
        "max_relation_tokens": 22000,
        "max_total_tokens": 90000,
        "why": "**这里是 `mix` 真正不可替代的地方**：多跳靠关系边，"
               "所以 `max_relation_tokens` 是全预设里最大的。"
               "chunk 也要给够，因为链条的中间环节常只出现在正文里。",
    },
    "sweep": {
        "label": "广域扫掠",
        "summary": "有哪些、完整经历、某个版本区间发生了什么",
        "when": "答案是「一批」而不是「一条」，需要尽量多的章节参与。"
                "例：「2.0 到 3.0 之间有哪些重大事件」",
        "latency": "低",
        "cost": "最高",
        "mode": "naive",
        "top_k": 40,
        "chunk_top_k": 150,
        "max_entity_tokens": 2000,
        "max_relation_tokens": 2000,
        "max_total_tokens": 140000,
        "extra": {"enable_rerank": False},
        "why": "枚举型问题要广度而非精度：用 `naive`、图预算压到最小、总预算开到最大。"
               "**反直觉但实测如此 —— 它的检索比 `mix` 更快（3.3s vs 6.4s）而覆盖"
               "是 2.3 倍（49 章 vs 21 章）**；真正的代价在生成端：答案长、上下文大，"
               "端到端实测 69s（其余预设 5–45s）。"
               "关掉 rerank 是因为预算足够装下全部候选，重排只改顺序不减内容，"
               "关掉省 0.8s 且覆盖不变（48 vs 49 章）。",
    },
    "quick": {
        "label": "快速应答",
        "summary": "只要快，连续追问或边打字边出结果",
        "when": "对延迟敏感，可以接受召回变小。例：多轮追问、流式界面",
        "latency": "最低",
        "cost": "最低",
        "mode": "naive",
        "top_k": 20,
        "chunk_top_k": 15,
        "max_entity_tokens": 2000,
        "max_relation_tokens": 2000,
        "max_total_tokens": 20000,
        "why": "延迟优先的极端档：`naive` + 最小预算，实测检索 2.7s。"
               "保留 rerank —— 实测关掉只省 0.3s 却少命中 1 章，不划算。"
               "**代价是召回明显变小，宽泛问题不该用它。**",
    },
}

# 前端展示顺序：由窄到宽，最后是延迟优先档
PRESET_ORDER = ["pinpoint", "lookup", "chain", "sweep", "quick"]

DEFAULT_PRESET = "pinpoint"

# 字段分组，便于 for_ui() / params() 各自取用
_UI_FIELDS = ("label", "summary", "when", "latency", "cost")
_PARAM_FIELDS = ("mode", "top_k", "chunk_top_k",
                 "max_entity_tokens", "max_relation_tokens", "max_total_tokens")


@dataclass
class Plan:
    """一次查询的规划结果。"""

    name: str
    label: str
    summary: str
    when: str
    latency: str
    cost: str
    mode: str
    top_k: int
    chunk_top_k: int
    max_entity_tokens: int
    max_relation_tokens: int
    max_total_tokens: int
    why: str = ""
    question: str = ""
    extra: dict = field(default_factory=dict)

    def params(self) -> dict:
        """合并进 `/query` 请求体的检索参数（不含 query 本身）。"""
        d = {k: getattr(self, k) for k in _PARAM_FIELDS}
        d.update(self.extra)
        return d

    def as_dict(self) -> dict:
        return asdict(self)


def get_preset(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"未知预设 {name!r}；可选: {', '.join(PRESET_ORDER)}")
    return PRESETS[name]


def plan(preset: str | None = None, question: str = "", **overrides) -> Plan:
    """取一组检索参数。

    preset 为空时用 DEFAULT_PRESET。overrides 覆盖检索参数（供实验用），
    会与预设自带的 extra 合并。
    """
    name = preset or DEFAULT_PRESET
    base = dict(get_preset(name))
    why = base.pop("why", "")
    extra = dict(base.pop("extra", {}))
    for k in overrides:
        if k in extra:
            extra[k] = overrides.pop(k)
    base.update(overrides)
    return Plan(name=name, why=why, extra=extra, question=question, **base)


def for_ui() -> list[dict]:
    """给前端的预设选项列表（展示元数据 + 参数摘要，不含 why）。"""
    out = []
    for name in PRESET_ORDER:
        p = PRESETS[name]
        # ⚠️ 必须显式标注：`{"name": name}` 不标注会被推成 `dict[str, str]`，
        # 而 `p`（来自 `PRESETS: dict[str, dict]`）取出来的是 Unknown —— 于是
        # 下一行的 `item.update({k: p.get(k) …})` 与 `item["params"] = {…}`
        # 都会报 reportArgumentType。标注成 `dict[str, Any]` 后三处一起消失。
        # 只影响静态检查，运行时行为完全不变（改前改后 `--json` 输出逐字节相同）。
        item: dict[str, Any] = {"name": name}
        item.update({k: p.get(k) for k in _UI_FIELDS})
        item["params"] = {k: p[k] for k in _PARAM_FIELDS}
        item["params"].update(p.get("extra", {}))
        out.append(item)
    return out


def describe() -> str:
    """命令行用的预设总表。"""
    lines = [
        f"{'预设':<10}{'mode':<7}{'top_k':>6}{'chunk':>7}"
        f"{'entity':>8}{'relation':>10}{'total':>8}{'rerank':>8}  {'检索':<6}{'花费':<6}名称",
        "-" * 108,
    ]
    for name in PRESET_ORDER:
        p = PRESETS[name]
        rr = p.get("extra", {}).get("enable_rerank", True)
        lines.append(
            f"{name:<10}{p['mode']:<7}{p['top_k']:>6}{p['chunk_top_k']:>7}"
            f"{p['max_entity_tokens']:>8}{p['max_relation_tokens']:>10}"
            f"{p['max_total_tokens']:>8}{('on' if rr else 'off'):>8}  "
            f"{p['latency']:<6}{p['cost']:<6}{p['label']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import io
    import sys

    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    argv = sys.argv[1:]
    if argv and argv[0] == "--json":
        print(json.dumps(for_ui(), ensure_ascii=False, indent=2))
    elif argv and argv[0] not in ("--list", "-l"):
        p = plan(argv[0])
        print(f"预设: {p.name} — {p.label}")
        print(f"说明: {p.summary}")
        print(f"适合: {p.when}")
        print(f"档位: 检索延迟 {p.latency} / 花费 {p.cost}")
        print(f"取舍: {p.why}")
        print(f"参数: {p.params()}")
    else:
        print(describe())
