import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, looksUngrounded, streamQuery, type QueryFilter } from '../api/client'
import type { FilterInfo, Preset, ReferenceItem, Stage } from '../api/types'
import { splitThinking } from '../lib/think'

export interface AnswerState {
  question: string
  preset: string
  text: string
  refs: ReferenceItem[]
  stage: Stage
  /** 分段进度里后端报上来的原始步骤名 */
  step: string | null
  error: string | null
  elapsed: number
  responseTime: number | null
  /** 推断为"没有可靠依据"（无引用或固定兜底文案）—— UI 必须标注 */
  ungrounded: boolean
  running: boolean
  /** 薄服务层回报的过滤情况（透传时 active=false；没有服务层时为 null） */
  filterInfo: FilterInfo | null
}

const INITIAL: AnswerState = {
  question: '',
  preset: '',
  text: '',
  refs: [],
  stage: 'idle',
  step: null,
  error: null,
  elapsed: 0,
  responseTime: null,
  ungrounded: false,
  running: false,
  filterInfo: null,
}

/** 后端 progress 事件名 → 我们的阶段（按子串匹配，避免绑死字符串）。 */
function stageFor(step: string): Stage {
  const s = step.toLowerCase()
  if (s.includes('keyword')) return 'extracting'
  if (s.includes('rerank')) return 'reranking'
  if (s.includes('generat') || s.includes('response')) return 'generating'
  if (s.includes('retriev') || s.includes('entit') || s.includes('relation') || s.includes('chunk')) return 'retrieving'
  return 'retrieving'
}

export const STAGE_LABEL: Record<Stage, string> = {
  idle: '待机',
  extracting: '抽关键词',
  retrieving: '检索',
  reranking: '重排',
  generating: '生成中',
  done: '完成',
  error: '失败',
}

const STAGE_ORDER: Stage[] = ['extracting', 'retrieving', 'reranking', 'generating']

export function stageIndex(s: Stage): number {
  const i = STAGE_ORDER.indexOf(s)
  return i < 0 ? (s === 'done' ? STAGE_ORDER.length : -1) : i
}

export function useQueryRunner() {
  const [state, setState] = useState<AnswerState>(INITIAL)
  const abortRef = useRef<AbortController | null>(null)
  const timerRef = useRef<number | null>(null)

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => stopTimer, [stopTimer])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    stopTimer()
    setState((s) => ({ ...s, running: false, stage: s.stage === 'error' ? 'error' : 'done' }))
  }, [stopTimer])

  const run = useCallback(
    async (question: string, preset: Preset, filter: QueryFilter | null = null) => {
      abortRef.current?.abort()
      const ac = new AbortController()
      abortRef.current = ac
      stopTimer()

      const startedAt = performance.now()
      setState({
        ...INITIAL,
        question,
        preset: preset.name,
        stage: 'retrieving',
        running: true,
      })
      timerRef.current = window.setInterval(() => {
        setState((s) => (s.running ? { ...s, elapsed: (performance.now() - startedAt) / 1000 } : s))
      }, 200)

      let text = ''
      let refs: ReferenceItem[] = []
      let gotError: string | null = null

      try {
        await streamQuery(
          {
            query: question,
            preset: preset.name,
            mode: preset.mode,
            top_k: preset.top_k,
            chunk_top_k: preset.chunk_top_k,
            max_entity_tokens: preset.max_entity_tokens,
            max_relation_tokens: preset.max_relation_tokens,
            max_total_tokens: preset.max_total_tokens,
            enable_rerank: preset.enable_rerank,
            filter: filter ?? undefined,
            include_progress: true, // 要分段进度：69s 的档位没它会以为卡死
            stream: true,
          },
          {
            onFilter: (info) => {
              setState((s) => ({ ...s, filterInfo: info }))
            },
            onReferences: (r) => {
              refs = r
              setState((s) => ({ ...s, refs: r }))
            },
            onProgress: (step) => {
              const st = stageFor(step)
              setState((s) => ({ ...s, step, stage: st }))
            },
            onDelta: (chunk) => {
              text += chunk
              setState((s) => ({ ...s, text, stage: s.stage === 'generating' ? s.stage : 'generating' }))
            },
            onError: (msg) => {
              gotError = msg
            },
          },
          ac.signal,
        )
        stopTimer()
        const elapsed = (performance.now() - startedAt) / 1000
        // 「有没有可靠依据」必须拿**剥掉思考块之后**的正文判断，
        // 否则思维链里出现的引用字样会把空回答误判成 grounded。
        const { answer } = splitThinking(text)
        setState((s) => ({
          ...s,
          text,
          refs,
          elapsed,
          running: false,
          stage: 'done',
          ungrounded: looksUngrounded(answer, refs.length),
        }))
      } catch (e) {
        stopTimer()
        if (ac.signal.aborted) return
        const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
        setState((s) => ({
          ...s,
          text,
          refs,
          running: false,
          stage: 'error',
          elapsed: (performance.now() - startedAt) / 1000,
          error: gotError ?? msg,
        }))
      } finally {
        if (abortRef.current === ac) abortRef.current = null
      }
    },
    [stopTimer],
  )

  return { state, run, stop }
}
