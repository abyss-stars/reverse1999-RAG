import type { FilterInfo, ReferenceItem, StreamLine } from './types'

declare global {
  interface Window {
    __LIGHTRAG_CONFIG__?: {
      apiPrefix?: string
      webuiPrefix?: string
      webuiTitle?: string
    }
  }
}

/**
 * 后端基址。
 *
 * 默认走**薄服务层**（`/api`，L3b）：它承载版本/章节过滤与预设下发，
 * 不设过滤时把请求原样透传给 LightRAG。开发期由 vite 代理到 :8787。
 *
 * 上线形态由薄服务层一并托管静态产物 → 前端与 API 同源。
 * 若把 `VITE_API_BASE` 设成 `/lightrag`，则绕过薄服务层直连 LightRAG
 * （应急通道，见 vite.config.ts 的 /lightrag 代理）。
 *
 * 挂进 LightRAG 容器 webui 目录时（纯静态形态），后端会注入
 * `window.__LIGHTRAG_CONFIG__.apiPrefix`，这里优先用它。
 */
function apiBase(): string {
  const cfg = window.__LIGHTRAG_CONFIG__
  if (cfg && typeof cfg.apiPrefix === 'string' && cfg.apiPrefix) {
    return cfg.apiPrefix.replace(/\/$/, '')
  }
  const fromEnv = import.meta.env.VITE_API_BASE as string | undefined
  return (fromEnv ?? '/api').replace(/\/$/, '')
}

/** 检索范围限定（薄服务层消费；服务层不支持时会忽略）。 */
export interface QueryFilter {
  categories?: string[]
  versions?: string[]
  sources?: string[]
  chapters?: string[]
  min_order?: number | null
  max_order?: number | null
}

// 这里曾有 `isFilterActive()` 与 `health()` 两个导出，**全仓无人调用**，已删（2026-09-27）。
// 判"范围是否生效"用的是 lib/chapter.ts 的 scopeActive()（那一份是按章节表算的，能顺带给出命中章数）；
// 后端探活则由 scripts/verify-app.mjs、scripts/status.ps1 直接打 /api/health，
// 不经过前端代码 —— 所以删掉它们不减少任何能力，前端本就不做健康指示。

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const txt = await res.text()
    return txt.slice(0, 400) || res.statusText
  } catch {
    return res.statusText
  }
}

export interface StreamHandlers {
  onFilter?: (info: FilterInfo) => void
  onReferences?: (refs: ReferenceItem[]) => void
  onProgress?: (step: string) => void
  onDelta?: (text: string) => void
  onError?: (message: string) => void
  onDone?: (info: { responseTime?: number }) => void
}

/**
 * 走 `/query/stream`，按 NDJSON 逐行解析。
 *
 * ⚠️ 协议要点（见 LightRAG 的 StreamChunkResponse 文档）：
 * 默认 `include_progress=false` 时 references 保证是**第一行**；
 * 一旦开启 progress，progress 行会插到 references 之前 ——
 * 所以这里**只按键分派，不依赖行序**。
 */
export async function streamQuery(
  body: Record<string, unknown>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${apiBase()}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) throw new ApiError(await readError(res), res.status)
  if (!res.body) throw new ApiError('响应没有 body，无法流式读取')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sawError: string | null = null

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let nl: number
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl).trim()
        buffer = buffer.slice(nl + 1)
        if (!line) continue
        let obj: StreamLine
        try {
          obj = JSON.parse(line) as StreamLine
        } catch {
          continue // 半行/脏行：跳过，不中断整条流
        }
        if ('filter' in obj && obj.filter) handlers.onFilter?.(obj.filter)
        else if ('references' in obj && Array.isArray(obj.references)) handlers.onReferences?.(obj.references)
        else if ('progress' in obj && typeof obj.progress === 'string') handlers.onProgress?.(obj.progress)
        else if ('response' in obj && typeof obj.response === 'string') handlers.onDelta?.(obj.response)
        else if ('error' in obj && typeof obj.error === 'string') {
          sawError = obj.error
          handlers.onError?.(obj.error)
        } else if ('response_time' in obj && typeof obj.response_time === 'number') {
          handlers.onDone?.({ responseTime: obj.response_time })
        }
      }
    }
    // 收尾：最后一行可能没有换行符
    const tail = buffer.trim()
    if (tail) {
      try {
        const obj = JSON.parse(tail) as StreamLine
        if ('response' in obj && typeof obj.response === 'string') handlers.onDelta?.(obj.response)
        else if ('references' in obj && Array.isArray(obj.references)) handlers.onReferences?.(obj.references)
        else if ('response_time' in obj && typeof obj.response_time === 'number') handlers.onDone?.({ responseTime: obj.response_time })
      } catch {
        /* 忽略 */
      }
    }
  } finally {
    reader.releaseLock()
  }

  if (sawError) throw new ApiError(sawError)
}

/** LightRAG 在"检索不到任何上下文"时返回的固定兜底文案。 */
const NO_CONTEXT_RE = /no relevant context found/i

/**
 * 流式协议**不返回** `llm_generated`（只有 /query 返回），
 * 所以这里用两个可观测信号推断"这条回答是不是真的基于检索结果"：
 *   ① 一个引用都没有；② 正文就是那句固定兜底文案。
 * 推断为真时 UI 必须明确标注，不能让它冒充正常答案。
 */
export function looksUngrounded(text: string, refCount: number): boolean {
  return refCount === 0 || NO_CONTEXT_RE.test(text)
}
