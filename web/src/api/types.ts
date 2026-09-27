/** 与 LightRAG `/query` 系列端点对齐的类型（依据 LightRAG/lightrag/api/routers/query_routes.py）。 */

export type Mode = 'naive' | 'local' | 'global' | 'hybrid' | 'mix' | 'bypass'

/** 检索档位定义。数值真源是 pipeline/lib/query_planner.py（见 presets.ts 头部）。 */
export interface Preset {
  name: string
  label: string
  summary: string
  /** 什么情况下该选它（来自 query_planner 的 when 文案） */
  when: string
  /** 「低 / 中 / 中高 / 最高 / 最低」——检索延迟档 */
  latency: string
  /** 花费档。与 latency 刻意分开：sweep 检索最快但花费最高。 */
  cost: string
  mode: Mode
  top_k: number
  chunk_top_k: number
  max_entity_tokens: number
  max_relation_tokens: number
  max_total_tokens: number
  enable_rerank: boolean
}

/** 引用条目。`content` 仅在 include_chunk_content=true 时返回。 */
export interface ReferenceItem {
  reference_id: string
  file_path: string
  content?: string[] | null
}

// 这里曾有 `QueryResponse`（/query 非流式契约）、`HealthInfo`（/api/health 契约）。
// 两者都是**定义了没有任何消费方**的死类型，已删（2026-09-27）：
// 前端只走 `/query/stream`（逐行 NDJSON，见下面的 StreamLine），从不调非流式 /query；
// 后端探活由 scripts/verify-app.mjs、scripts/status.ps1 直接打 HTTP，不经过前端。
// 需要这两个端点的契约时以 LightRAG/lightrag/api/routers/query_routes.py 与 server/app.py 为准。

/** 薄服务层在流首行回报的过滤情况（透传时 active=false）。 */
export interface FilterInfo {
  active: boolean
  note?: string
  spec?: string
  matched_chapters?: number
  chapters?: string[]
  error?: string
  retrieval_seconds?: number
  prune?: {
    chunks_before: number
    chunks_after: number
    refs_before: number
    refs_after: number
    kg_dropped: boolean
    dropped_ref_ids: string[]
    kept_ref_ids: string[]
  }
}

/** /query/stream 的 NDJSON 行（键决定类型，不能依赖行序）。 */
export type StreamLine =
  | { filter: FilterInfo }
  | { references: ReferenceItem[] }
  | { response: string }
  | { progress: string }
  | { error: string }
  | { response_time: number }

/** 检索阶段（用于分段进度显示） */
export type Stage = 'idle' | 'extracting' | 'retrieving' | 'reranking' | 'generating' | 'done' | 'error'
