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

export interface QueryResponse {
  response: string
  references?: ReferenceItem[] | null
  response_time?: number | null
  /** false = 这段文字不是回答模型写的（无上下文兜底 / 调试输出）。UI 必须据此打标。 */
  llm_generated: boolean
}

export interface HealthInfo {
  status: string
  core_version?: string
  auth_mode?: string
  webui_available?: boolean
  webui_title?: string
  configuration?: Record<string, unknown>
}

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

export interface ProgressEvent {
  stage: Stage
  label: string
}
