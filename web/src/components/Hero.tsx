import type { FC } from 'react'
import { CORPUS_LOCK, INDEX_STATS } from '../lib/stats'
import type { Quote } from '../lib/quote'

const DOW = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
const pad = (n: number) => String(n).padStart(2, '0')

/**
 * Hero：衬线大标题 + 铜色日期块 + 今日台词 + 索引概况卡。
 * 日期格式（`MM / TODAY · DD / DOW.YYYY`）与台词块的排版语言都来自参考站。
 */
export const Hero: FC<{ quote: Quote | null; chapters: number | null }> = ({ quote, chapters }) => {
  const now = new Date()
  const n = (v: number | null) => (v === null ? '—' : v.toLocaleString('en-US'))

  return (
    <section className="hero">
      <div className="wrap">
        <div>
          <p className="hero-title-en en">Reverse: 1999 — Simplified Chinese Story Index</p>
          <h1>剧情档案</h1>
          <p className="hero-sub">把 81 章剧情当作一份可检索的档案，而不是一份目录。</p>

          <div className="dateblock">
            <span className="db-day">{pad(now.getMonth() + 1)}</span>
            <span className="db-col">
              <span className="db-today">TODAY</span>
              <span className="db-rest">/</span>
            </span>
            <span className="db-day">{pad(now.getDate())}</span>
            <span className="db-col">
              <span className="db-today" style={{ color: 'var(--ink-2)' }}>
                {DOW[now.getDay()]}
              </span>
              <span className="db-rest">{now.getFullYear()}</span>
            </span>
          </div>

          {quote ? (
            <blockquote className="quote">
              「{quote.text}」
              <cite>—— {quote.source}　[每日轮换，取自本地语料]</cite>
            </blockquote>
          ) : (
            <blockquote className="quote">
              「——」
              <cite>[今日台词未生成：跑 python scripts/gen_web_quotes.py]</cite>
            </blockquote>
          )}
        </div>

        <aside className="infobox">
          <h2>
            索引概况<small>Index Overview</small>
          </h2>
          <dl style={{ margin: 0 }}>
            <div className="stat">
              <dt>剧情章节</dt>
              <dd>{chapters ?? INDEX_STATS.chapters}</dd>
            </div>
            <div className="stat">
              <dt>图谱实体</dt>
              <dd>{n(INDEX_STATS.entities)}</dd>
            </div>
            <div className="stat">
              <dt>实体关系</dt>
              <dd>{n(INDEX_STATS.relations)}</dd>
            </div>
            <div className="stat">
              <dt>文本块</dt>
              <dd>{n(INDEX_STATS.chunks)}</dd>
            </div>
            <div className="stat">
              <dt>抽取缓存</dt>
              <dd>{n(INDEX_STATS.cache)}</dd>
            </div>
          </dl>
          <p className="note">
            全量已建索引并通过回归（10/10）。语料锁定 <span className="mono">{CORPUS_LOCK}</span>。
          </p>
        </aside>
      </div>
    </section>
  )
}
