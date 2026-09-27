import { useCallback, useEffect, useMemo, useRef, useState, type FC } from 'react'
import { PRESET_BY_NAME } from '../api/presets'
import type { ReferenceItem } from '../api/types'
import { STAGE_LABEL, stageIndex, type AnswerState } from '../hooks/useQueryRunner'
import { chapterForPath, VERSION_SOURCE_NOTE, type ChapterRecord } from '../lib/chapter'
import { renderAnswer } from '../lib/miniMarkdown'
import { splitThinking } from '../lib/think'

const STAGES = ['extracting', 'retrieving', 'reranking', 'generating'] as const

/**
 * 引用卡默认只展示前 N 条：pinpoint 档常命中 20+ 章，全展开会把页面拉到几千像素。
 * 取 4 是因为英雄区之下第一屏能完整放下 4 张卡而不必滚动。
 */
const REFS_COLLAPSED = 4

interface Props {
  state: AnswerState
  fileMap: Map<string, ChapterRecord> | null
  onAskChapter: (c: ChapterRecord) => void
  /**
   * 打开该引用所属章节在「章节档案」页的条目（跳过去并高亮）。
   *
   * 这是「引用可追溯」的落点：只给「就这一章提问」的话，用户能就这一章发问、
   * 却没有任何入口去**看**这一章的档案（版本、来源、阅读顺序）。
   * 可选：不传则不渲染这个按钮（章节页自己不需要它）。
   */
  onOpenChapter?: (c: ChapterRecord) => void
}

export const AnswerPanel: FC<Props> = ({ state, fileMap, onAskChapter, onOpenChapter }) => {
  const [active, setActive] = useState<number | null>(null)
  const [showAllRefs, setShowAllRefs] = useState(false)
  /**
   * 被正文角标「临时提升」为可见的引用（按 reference_id 记）。
   * 没有它的话，答案里写 `[7]`、而第 7 条落在折叠区时，点角标会**点不动** ——
   * 正文列了出处、界面上却找不到，看起来就像 bug。见下面的 jump()。
   */
  const [revealed, setRevealed] = useState<Set<number>>(() => new Set())
  /** 待滚动的角标号：提升后要等重渲染完、卡片真的在 DOM 里才好滚，故延后一帧。 */
  const [pendingJump, setPendingJump] = useState<number | null>(null)

  /** 上一轮的 (question, running)：用来只在「新一轮开始」时清状态。 */
  const prevRun = useRef({ question: '', running: false })

  /**
   * 只在**新一轮开始**（running 由 false 变 true）或换了问题时清掉高亮/展开/提升。
   *
   * ⚠️ 绝不能在 `running` 变 false（流结束）时清 —— 这一条踩过坑：
   * 流式过程中用户就能展开引用、点正文角标，而"答案落地"和"用户此刻的点击"
   * 可能落在同一帧附近。若在结束时无条件重置，用户刚点开的卡片会被静默收回，
   * 看起来就是"点了没反应"。
   *
   * 实测复现：E2E 在答案落地后立刻点角标提升，`Page.captureScreenshot`
   * （整页截图，正文很长时很慢）阻塞了渲染进程，把 React 的 passive effect
   * 冲刷推迟到点击之后 —— 于是 completion 的那次重置把刚做的提升抹掉了。
   * 加了这条守卫后同样的点击稳定生效。
   */
  useEffect(() => {
    const prev = prevRun.current
    const startedNewRun = state.running && !prev.running
    prevRun.current = { question: state.question, running: state.running }
    if (!startedNewRun && state.question === prev.question) return
    setActive(null)
    setShowAllRefs(false)
    setRevealed(new Set())
    setPendingJump(null)
  }, [state.question, state.running])

  const current = stageIndex(state.stage)
  const preset = PRESET_BY_NAME[state.preset]

  const jump = useCallback(
    (n: number) => {
      setActive(n)
      // 落在折叠区里的角标：先把它提升为可见，再滚动。
      // 判定放在 updater 里，避免 memo 化的正文闭包捕获过期的 revealed。
      setRevealed((prev) => {
        const idx = state.refs.findIndex((r) => Number(r.reference_id) === n)
        if (idx < REFS_COLLAPSED || prev.has(n)) return prev
        const next = new Set(prev)
        next.add(n)
        return next
      })
      setPendingJump(n)
    },
    [state.refs],
  )

  // 提升引起的重渲染落地后，卡片才在 DOM 里 —— 这时滚才滚得到。
  useEffect(() => {
    if (pendingJump === null) return
    const el = document.getElementById(`ref-${pendingJump}`)
    // 不用 scrollIntoView：在 iframe 预览里会连带滚动外层框架
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 90, behavior: 'smooth' })
    setPendingJump(null)
  }, [pendingJump, revealed, showAllRefs])

  /** 实际渲染的引用：前 N 条 + 被角标提升的那些，保持检索原序。 */
  const visibleRefs = useMemo(() => {
    if (showAllRefs) return state.refs
    return state.refs.filter((r, i) => i < REFS_COLLAPSED || revealed.has(Number(r.reference_id)))
  }, [state.refs, showAllRefs, revealed])

  const headCount = Math.min(REFS_COLLAPSED, state.refs.length)
  const promotedCount = visibleRefs.length - headCount
  const hiddenCount = state.refs.length - visibleRefs.length

  // 思考块内联在 content 流里，必须先剥掉再渲染（见 lib/think.ts）
  const { thinking, answer, thinkingOpen } = useMemo(() => splitThinking(state.text), [state.text])

  const body = useMemo(() => (answer ? renderAnswer(answer, jump, active) : null), [answer, jump, active])

  const hasAny = state.question !== ''

  return (
    <>
      <div className="status">
        {STAGES.map((s, i) => {
          const cls = current > i || state.stage === 'done' ? 'chip done' : current === i && state.running ? 'chip on' : 'chip'
          return (
            <span key={s} className={cls}>
              {STAGE_LABEL[s]}
              {current === i && state.running ? '…' : ''}
            </span>
          )
        })}
        <span className="spent">
          {state.running && <span className="spin" style={{ marginRight: 8 }} />}
          {state.elapsed.toFixed(1)}s
          {state.refs.length > 0 && <>　·　命中 {state.refs.length} 章</>}
          {state.responseTime !== null && <>　·　后端 {state.responseTime.toFixed(2)}s</>}
        </span>
      </div>

      {state.error && (
        <div className="err">
          检索失败：{state.error}
          <br />
          <span style={{ opacity: 0.8 }}>
            常见原因：后端未启动、或百炼账号欠费（embedding 被拒会让所有模式返回空）。
          </span>
        </div>
      )}

      {state.filterInfo?.active && !state.error && (
        <div className="scope-report">
          <span className="k">已限定检索范围</span>
          <span className="v">{state.filterInfo.spec}</span>
          {state.filterInfo.prune && (
            <span className="v muted">
              上下文片段 {state.filterInfo.prune.chunks_before} → {state.filterInfo.prune.chunks_after}
              {'　·　'}引用 {state.filterInfo.prune.refs_before} → {state.filterInfo.prune.refs_after}
              {state.filterInfo.prune.kg_dropped && '　·　已移除图谱上下文'}
            </span>
          )}
        </div>
      )}

      {hasAny && (
        <section className="answer">
          <article className="card">
            <div className="card-head">
              <span className="q">{state.question}</span>
              {preset && <span className="tag">{preset.label}</span>}
            </div>

            <div className="ans-body">
              {state.ungrounded && (
                <p className="ph-note">
                  未检索到可靠依据 —— 这条回答没有引用；不要把它当作出处可考的结论。
                </p>
              )}

              {thinking && (
                <details className="think">
                  <summary>
                    思考过程（{thinking.length} 字）{thinkingOpen ? ' · 进行中' : ''}
                  </summary>
                  <div className="think-body">{thinking}</div>
                </details>
              )}

              {answer ? (
                body
              ) : state.running ? (
                <p className="ph-note">
                  {thinkingOpen ? '模型正在思考…' : '正在检索并生成…'}
                  （{STAGE_LABEL[state.stage]}
                  {state.step ? `：${state.step}` : ''}）
                </p>
              ) : (
                <p className="ph-note">没有拿到回答正文。</p>
              )}
            </div>

            {!state.running && state.text && (
              <div className="readout">
                elapsed {state.elapsed.toFixed(1)}s
                {state.responseTime !== null && <>　·　response_time {state.responseTime.toFixed(2)}s</>}
                {'　·　'}
                refs {state.refs.length}
                {'　·　'}
                {state.ungrounded ? 'ungrounded (无引用)' : 'grounded'}
              </div>
            )}
          </article>

          <aside className="card refs">
            <h3>
              引用（
              {visibleRefs.length < state.refs.length
                ? `${visibleRefs.length} / ${state.refs.length}`
                : state.refs.length}
              ）
              <span className="en" style={{ fontSize: 9.5, color: 'var(--muted-en)' }}>
                {' '}
                References
              </span>
            </h3>
            {state.refs.length === 0 && (
              <div className="ref">
                <div className="where">{state.running ? '检索中…' : '这次没有检索到可引用的章节。'}</div>
              </div>
            )}
            {visibleRefs.map((r) => (
              <RefCard
                key={r.reference_id}
                ref_={r}
                chapter={fileMap ? chapterForPath(fileMap, r.file_path) : undefined}
                active={active === Number(r.reference_id)}
                onAskChapter={onAskChapter}
                onOpenChapter={onOpenChapter}
              />
            ))}
            {(hiddenCount > 0 || showAllRefs) && (
              <div className="ref">
                <button type="button" className="cite" style={{ padding: '4px 12px' }} onClick={() => setShowAllRefs((v) => !v)}>
                  {showAllRefs ? `收起（只显示前 ${REFS_COLLAPSED} 条）` : `展开全部 ${state.refs.length} 条引用`}
                </button>
                {!showAllRefs && (
                  <div className="where" style={{ marginTop: 8 }}>
                    已按检索顺序列出前 {REFS_COLLAPSED} 条
                    {promotedCount > 0 && `，另有 ${promotedCount} 条因点击角标临时展开`}
                    ；其余 {hiddenCount} 条默认收起。
                  </div>
                )}
              </div>
            )}
          </aside>
        </section>
      )}
    </>
  )
}

const RefCard: FC<{
  ref_: ReferenceItem
  chapter: ChapterRecord | undefined
  active: boolean
  onAskChapter: (c: ChapterRecord) => void
  onOpenChapter?: (c: ChapterRecord) => void
}> = ({ ref_, chapter, active, onAskChapter, onOpenChapter }) => {
  const snippet = ref_.content?.find((c) => c && c.trim().length > 0)
  const n = Number(ref_.reference_id)

  return (
    <div className="ref" id={`ref-${n}`} data-active={active ? 'true' : 'false'}>
      <div className="top">
        <span className="no">[{n}]</span>
        <span className="file">{ref_.file_path}</span>
      </div>

      {chapter ? (
        <>
          <div className="where">
            第 {chapter.order} 章 · {chapter.chapter_no} {chapter.title} · {chapter.category_label} ·{' '}
            {chapter.episodes} 单元
          </div>
          {snippet && <div className="snip">「{snippet.replace(/\s+/g, ' ').slice(0, 160)}…」</div>}
          <span className="ver" title={VERSION_SOURCE_NOTE[chapter.version_source ?? 'null'] ?? ''}>
            v{chapter.version ?? '未知'} · {chapter.version_source ?? '无来源'}
          </span>
          <button
            type="button"
            className="cite"
            style={{ marginLeft: 8, padding: '2px 8px' }}
            onClick={() => onAskChapter(chapter)}
          >
            就这一章提问
          </button>
          {onOpenChapter && (
            <button
              type="button"
              className="cite open-chapter"
              style={{ marginLeft: 6, padding: '2px 8px' }}
              onClick={() => onOpenChapter(chapter)}
            >
              在章节档案中查看
            </button>
          )}
        </>
      ) : (
        <>
          {snippet && <div className="snip">「{snippet.replace(/\s+/g, ' ').slice(0, 160)}…」</div>}
          <div className="where">未在章节表里匹配到该文件</div>
        </>
      )}
    </div>
  )
}
