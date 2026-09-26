import { useEffect, useRef, useState, type FC } from 'react'
import { PRESET_BY_NAME, PRESETS } from '../api/presets'
import { AnswerPanel } from '../components/AnswerPanel'
import { Hero } from '../components/Hero'
import { PresetGrid } from '../components/PresetGrid'
import { ScopeFilter, toQueryFilter } from '../components/ScopeFilter'
import { SearchIcon } from '../components/Icons'
import { useQueryRunner } from '../hooks/useQueryRunner'
import { navigate } from '../lib/hashRoute'
import type { ChapterRecord, ChapterIndex, ScopeFilter as Scope } from '../lib/chapter'
import type { Quote } from '../lib/quote'

interface Props {
  index: ChapterIndex | null
  fileMap: Map<string, ChapterRecord> | null
  quotes: Quote[]
  initialQuestion: string
  initialPreset: string
  initialScope: Scope
}

/** 把范围编码进 hash，让"限定范围 + 问题 + 档位"整体可分享。 */
function scopeToHash(s: Scope): string {
  const parts: string[] = []
  if (s.versions?.length) parts.push(`ver=${encodeURIComponent(s.versions.join(','))}`)
  if (s.categories?.length) parts.push(`cat=${encodeURIComponent(s.categories.join(','))}`)
  if (s.chapters?.length) parts.push(`ch=${encodeURIComponent(s.chapters.join(','))}`)
  return parts.join('&')
}

export const Home: FC<Props> = ({ index, fileMap, quotes, initialQuestion, initialPreset, initialScope }) => {
  const [preset, setPreset] = useState(initialPreset in PRESET_BY_NAME ? initialPreset : PRESETS[0].name)
  const [scope, setScope] = useState<Scope>(initialScope)
  const [text, setText] = useState(initialQuestion)
  const { state, run, stop } = useQueryRunner()
  const autorunDone = useRef(false)

  const submit = (q: string, p: string, s: Scope = scope) => {
    const question = q.trim()
    if (!question) return
    // 把「问题 + 档位 + 范围」写进 hash —— 分享链接天然可用（website.md G2）
    const extra = scopeToHash(s)
    navigate(`/?q=${encodeURIComponent(question)}&preset=${encodeURIComponent(p)}${extra ? `&${extra}` : ''}`)
    void run(question, PRESET_BY_NAME[p] ?? PRESETS[0], toQueryFilter(s))
  }

  // 带 q 参数进来时自动跑一次（分享链接/从章节页跳过来）。ref 防 StrictMode 双执行。
  useEffect(() => {
    if (autorunDone.current) return
    if (!initialQuestion.trim()) return
    autorunDone.current = true
    void run(initialQuestion.trim(), PRESET_BY_NAME[initialPreset] ?? PRESETS[0], toQueryFilter(initialScope))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const askChapter = (c: ChapterRecord) => {
    const q = `《${c.title}》（${c.chapter_no}）讲了什么？`
    setText(q)
    submit(q, 'lookup', scope)
  }

  return (
    <>
      <Hero quote={quotes.length ? quotes[new Date().getDate() % quotes.length] : null} chapters={index?.total ?? null} />

      <div className="wrap">
        <section className="search">
          <div className="search-row">
            <label className="field">
              <SearchIcon />
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') submit(text, preset)
                }}
                placeholder="例：「这是我的箱子」是谁说的　·　回车即检索"
                autoComplete="off"
                aria-label="提问"
              />
            </label>
            {state.running ? (
              <button type="button" className="ask" onClick={stop}>
                停止
              </button>
            ) : (
              <button type="button" className="ask" onClick={() => submit(text, preset)} disabled={!text.trim()}>
                检索
              </button>
            )}
          </div>
        </section>

        <PresetGrid value={preset} onChange={setPreset} disabled={state.running} />

        <ScopeFilter index={index} value={scope} onChange={setScope} disabled={state.running} />

        <AnswerPanel state={state} fileMap={fileMap} onAskChapter={askChapter} />

        {!state.running && state.stage === 'idle' && (
          <p className="empty">
            输入问题即可检索。五档预设决定检索广度与花费：不确定就先用「精确定位」。
          </p>
        )}
      </div>
    </>
  )
}
