/* 由 query_planner.py 的 --json 输出生成，请勿手改数值。
 * 重新生成：
 *   python pipeline/lib/query_planner.py --json > docs/ref/presets.json
 *   python scripts/gen_web_presets.py
 * （预设的唯一真源是 pipeline/lib/query_planner.py） */

import type { Preset } from './types'

export const PRESETS: Preset[] = [
  {
    name: "pinpoint",
    label: "精确定位",
    summary: "某句话是谁说的，或某个具体事实",
    when: "问题指向明确，答案就在一两段对话里。例：「『这是我的箱子』是谁说的」",
    latency: "低",
    cost: "低",
    mode: "naive",
    top_k: 40,
    chunk_top_k: 40,
    max_entity_tokens: 2000,
    max_relation_tokens: 2000,
    max_total_tokens: 32000,
    enable_rerank: true,
  },
  {
    name: "lookup",
    label: "专名检索",
    summary: "某个人物、组织或术语是什么",
    when: "问的是「X 是什么 / 是谁 / 什么意思」，目标是拿到该条目的定义与背景",
    latency: "中",
    cost: "中",
    mode: "local",
    top_k: 60,
    chunk_top_k: 25,
    max_entity_tokens: 9000,
    max_relation_tokens: 5000,
    max_total_tokens: 45000,
    enable_rerank: true,
  },
  {
    name: "chain",
    label: "关系链",
    summary: "谁和谁什么关系、为什么会这样、事情的先后顺序",
    when: "需要跨越多处线索串联，或要理清因果与时间线。例：「A 和 B 是什么关系」",
    latency: "中高",
    cost: "高",
    mode: "mix",
    top_k: 60,
    chunk_top_k: 30,
    max_entity_tokens: 12000,
    max_relation_tokens: 22000,
    max_total_tokens: 90000,
    enable_rerank: true,
  },
  {
    name: "sweep",
    label: "广域扫掠",
    summary: "有哪些、完整经历、某个版本区间发生了什么",
    when: "答案是「一批」而不是「一条」，需要尽量多的章节参与。例：「2.0 到 3.0 之间有哪些重大事件」",
    latency: "低",
    cost: "最高",
    mode: "naive",
    top_k: 40,
    chunk_top_k: 150,
    max_entity_tokens: 2000,
    max_relation_tokens: 2000,
    max_total_tokens: 140000,
    enable_rerank: false,
  },
  {
    name: "quick",
    label: "快速应答",
    summary: "只要快，连续追问或边打字边出结果",
    when: "对延迟敏感，可以接受召回变小。例：多轮追问、流式界面",
    latency: "最低",
    cost: "最低",
    mode: "naive",
    top_k: 20,
    chunk_top_k: 15,
    max_entity_tokens: 2000,
    max_relation_tokens: 2000,
    max_total_tokens: 20000,
    enable_rerank: true,
  },
]

export const PRESET_BY_NAME = Object.fromEntries(PRESETS.map(p => [p.name, p])) as Record<string, Preset>
