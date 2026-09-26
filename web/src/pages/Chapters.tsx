import { useMemo, useState, type FC } from 'react'
import { CATEGORY_ORDER, VERSION_SOURCE_NOTE, questionForChapter, type ChapterRecord, type ChapterIndex } from '../lib/chapter'
import { navigate } from '../lib/hashRoute'

interface Props {
  index: ChapterIndex | null
  error: string | null
}

const SOURCE_SHORT: Record<string, string> = {
  metadata: 'metadata（最权威）',
  wiki: 'wiki（逐章实测）',
  number_rule: 'number_rule（置信度较低）',
  null: '无来源',
}

function versionKey(v: string | null): number {
  if (!v) return -1
  const n = Number.parseFloat(v)
  return Number.isFinite(n) ? n : -1
}

export const Chapters: FC<Props> = ({ index, error }) => {
  const [category, setCategory] = useState<string>('all')
  const [version, setVersion] = useState<string>('all')
  const [source, setSource] = useState<string>('all')
  const [selected, setSelected] = useState<string | null>(null)

  const versions = useMemo(() => {
    if (!index) return []
    const set = new Set<string>()
    for (const c of index.chapters) if (c.version) set.add(c.version)
    return [...set].sort((a, b) => versionKey(a) - versionKey(b))
  }, [index])

  const rows = useMemo(() => {
    if (!index) return []
    return index.chapters.filter(
      (c) =>
        (category === 'all' || c.category === category) &&
        (version === 'all' || c.version === version) &&
        (source === 'all' || (c.version_source ?? 'null') === source),
    )
  }, [index, category, version, source])

  const counts = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of index?.chapters ?? []) m.set(c.category, (m.get(c.category) ?? 0) + 1)
    return m
  }, [index])

  const detail = rows.find((c) => c.chapter_no === selected)

  const ask = (c: ChapterRecord) => {
    // 把这一章作为检索范围带过去：`ch=章号`，首页的 ScopeFilter 会读它
    navigate(`/?q=${encodeURIComponent(questionForChapter(c))}&preset=lookup&ch=${encodeURIComponent(c.chapter_no)}`)
  }

  return (
    <div>
      <section className="hero compact">
        <div className="wrap">
          <h1>章节档案</h1>
          <p className="page-sub">
            {index ? (
              <>
                共 <b>{index.total}</b> 章 · 版本与来源逐章标注 · 数据来自{' '}
                <span className="mono">state/chapter_index.json</span>
              </>
            ) : (
              '正在读取章节表…'
            )}
          </p>
        </div>
      </section>

      <div className="wrap">
        {error && <div className="err">章节表读取失败：{error}</div>}

        <div className="filters" style={{ marginTop: 18 }}>
        <button type="button" aria-pressed={category === 'all'} onClick={() => setCategory('all')}>
          全部（{index?.total ?? 0}）
        </button>
        {CATEGORY_ORDER.map((k) => (
          <button key={k} type="button" aria-pressed={category === k} onClick={() => setCategory(k)}>
            {index?.chapters.find((c) => c.category === k)?.category_label ?? k}（{counts.get(k) ?? 0}）
          </button>
        ))}
      </div>

      <div className="filters">
        <span className="sep">版本</span>
        <button type="button" aria-pressed={version === 'all'} onClick={() => setVersion('all')}>
          全部
        </button>
        {versions.map((v) => (
          <button key={v} type="button" aria-pressed={version === v} onClick={() => setVersion(v)}>
            {v}
          </button>
        ))}
        <span className="sep" style={{ marginLeft: 12 }}>
          版本来源
        </span>
        <button type="button" aria-pressed={source === 'all'} onClick={() => setSource('all')}>
          全部
        </button>
        {['metadata', 'wiki', 'number_rule', 'null'].map((s) => (
          <button key={s} type="button" aria-pressed={source === s} onClick={() => setSource(s)}>
            {SOURCE_SHORT[s]}
          </button>
        ))}
      </div>

      <p className="empty" style={{ paddingTop: 0 }}>
        {rows.length} 章命中。版本来源可信度：{VERSION_SOURCE_NOTE.metadata}；{VERSION_SOURCE_NOTE.number_rule}。
      </p>

      <div className="chapter-grid">
        {rows.map((c) => (
          <button
            key={c.chapter_no}
            type="button"
            className="chapter"
            aria-pressed={selected === c.chapter_no}
            onClick={() => setSelected(selected === c.chapter_no ? null : c.chapter_no)}
          >
            <span className="num">{c.chapter_no}</span>
            <span className="ttl">{c.title}</span>
            <span className="tags">
              <span className="tag ver">v{c.version ?? '未知'}</span>
              <span className="tag">{c.category_label}</span>
              <span className="tag src">{c.version_source ?? '无来源'}</span>
            </span>
          </button>
        ))}
      </div>

      {detail && (
        <section className="card detail">
          <div className="card-head">
            <span className="q">
              {detail.chapter_no} · {detail.title}
            </span>
            <span className="tag">{detail.category_label}</span>
          </div>
          <div className="row">
            <span>
              阅读顺序 <b>{detail.order}</b>
            </span>
            <span>
              剧情单元 <b>{detail.episodes}</b>
            </span>
            <span>
              小径 <b>{detail.trails}</b>
            </span>
            <span>
              正文 <b>{Math.round(detail.bytes / 1024)} KB</b>
            </span>
            <span>
              版本 <b>v{detail.version ?? '未知'}</b>
            </span>
            <span>
              来源 <b>{detail.version_source ?? '无来源'}</b>
            </span>
            <button type="button" className="cite" style={{ padding: '3px 10px' }} onClick={() => ask(detail)}>
              就这一章提问
            </button>
          </div>
          <div className="snips">
            <div className="s">
              {VERSION_SOURCE_NOTE[detail.version_source ?? 'null'] ?? '该章版本号无来源，未作推断。'}
            </div>
            <div className="s" style={{ color: 'var(--muted)' }}>
              提示：本页的筛选只作用于**档案浏览**。要让检索本身只在这章范围内进行，
              请回到问答页用「检索范围」限定（走薄服务层的「检索 → 按章节过滤 → 生成」）；
              也可以直接点上面的「就这一章提问」，它会把问题与范围一起带过去。
            </div>
          </div>
        </section>
      )}
      </div>
    </div>
  )
}
