import { useEffect, useMemo, useState } from 'react'
import { Footer, Strip, TopBar } from './components/Chrome'
import { About } from './pages/About'
import { Chapters } from './pages/Chapters'
import { Home } from './pages/Home'
import { buildFileMap, loadChapterIndex, type ChapterIndex } from './lib/chapter'
import { useHashRoute } from './lib/hashRoute'
import { loadQuotes, type Quote } from './lib/quote'
import { INDEX_STATS } from './lib/stats'

export default function App() {
  const route = useHashRoute()
  const [index, setIndex] = useState<ChapterIndex | null>(null)
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [indexError, setIndexError] = useState<string | null>(null)

  useEffect(() => {
    loadChapterIndex()
      .then(setIndex)
      .catch((e: unknown) => setIndexError(e instanceof Error ? e.message : String(e)))
    void loadQuotes().then(setQuotes)
  }, [])

  // 遮罩曲线按页切换（见 app.css：非首页要把压实提前，否则正文落在背景最亮的窗口里）
  useEffect(() => {
    document.body.dataset.page = route.name
  }, [route.name])

  const fileMap = useMemo(() => (index ? buildFileMap(index) : null), [index])

  // 只有首页需要「从 hash 里带问题进来」；用 route 里的 query 原样传下去
  const q = route.query.get('q') ?? ''
  const preset = route.query.get('preset') ?? ''
  const initialScope = useMemo(() => {
    const ver = (route.query.get('ver') ?? '').split(',').filter(Boolean)
    const cat = (route.query.get('cat') ?? '').split(',').filter(Boolean)
    const chs = (route.query.get('ch') ?? '').split(',').filter(Boolean)
    const s: { versions?: string[]; categories?: string[]; chapters?: string[] } = {}
    if (ver.length) s.versions = ver
    if (cat.length) s.categories = cat
    if (chs.length) s.chapters = chs
    return s
  }, [route.query])
  const scopeKey = `${initialScope.versions?.join(',') ?? ''}|${initialScope.categories?.join(',') ?? ''}|${
    initialScope.chapters?.join(',') ?? ''
  }`

  return (
    <>
      <Strip chapters={index?.total ?? null} chunks={INDEX_STATS.chunks} />
      <TopBar current={route.name} />

      <main>
        {route.name === 'home' && (
          <Home
            key={`${q}|${preset}|${scopeKey}`}
            index={index}
            fileMap={fileMap}
            quotes={quotes}
            initialQuestion={q}
            initialPreset={preset}
            initialScope={initialScope}
          />
        )}
        {route.name === 'chapters' && (
          <Chapters index={index} error={indexError} focusCh={route.query.get('ch') ?? ''} />
        )}
        {route.name === 'about' && <About chapters={index?.total ?? null} presetSource="pipeline/lib/query_planner.py" />}
      </main>

      <Footer
        chapters={index?.total ?? null}
        chunks={INDEX_STATS.chunks}
        build={new Date().toISOString().slice(0, 10)}
      />
    </>
  )
}
