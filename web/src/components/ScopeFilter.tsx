import { useMemo, type FC } from 'react'
import type { QueryFilter } from '../api/client'
import {
  CATEGORY_ORDER,
  countMatching,
  describeScope,
  scopeActive,
  type ChapterIndex,
  type ScopeFilter as Scope,
} from '../lib/chapter'

interface Props {
  index: ChapterIndex | null
  value: Scope
  onChange: (f: Scope) => void
  disabled?: boolean
}

/**
 * 检索范围限定（薄服务层的版本/章节过滤）。
 *
 * 刻意做成**默认收起**：首页的主体是"选档位 + 提问"，
 * 范围限定是进阶动作（L3b 能力），
 * 收起时用一行摘要说明当前范围与命中章数，不占版面。
 */
export const ScopeFilter: FC<Props> = ({ index, value, onChange, disabled }) => {
  const versions = useMemo(() => {
    if (!index) return []
    const set = new Set<string>()
    for (const c of index.chapters) if (c.version) set.add(c.version)
    return [...set].sort((a, b) => Number.parseFloat(a) - Number.parseFloat(b))
  }, [index])

  const matched = countMatching(index, value)
  const active = scopeActive(value)

  const toggle = (key: 'categories' | 'versions', v: string) => {
    const cur = value[key] ?? []
    const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
    onChange({ ...value, [key]: next })
  }

  const chip = (on: boolean) => `filters-chip${on ? ' on' : ''}`

  return (
    <details className="scope" open={active}>
      <summary>
        <span className="scope-label">检索范围</span>
        <span className="scope-state">
          {active ? describeScope(value) : '全部章节'}
          {index && <>　·　命中 <b>{matched}</b> / {index.chapters.length} 章</>}
        </span>
        {active && (
          <button
            type="button"
            className="filters-chip"
            onClick={(e) => {
              e.preventDefault()
              onChange({})
            }}
          >
            清除
          </button>
        )}
      </summary>

      <div className="scope-body">
        <div className="scope-row">
          <span className="scope-key">版本</span>
          <div className="filters" style={{ margin: 0 }}>
            <button type="button" className={chip(!value.versions?.length)} disabled={disabled} onClick={() => onChange({ ...value, versions: [] })}>
              全部
            </button>
            {versions.map((v) => (
              <button
                key={v}
                type="button"
                className={chip(Boolean(value.versions?.includes(v)))}
                disabled={disabled}
                onClick={() => toggle('versions', v)}
              >
                {v}
              </button>
            ))}
          </div>
        </div>

        <div className="scope-row">
          <span className="scope-key">分类</span>
          <div className="filters" style={{ margin: 0 }}>
            <button type="button" className={chip(!value.categories?.length)} disabled={disabled} onClick={() => onChange({ ...value, categories: [] })}>
              全部
            </button>
            {CATEGORY_ORDER.map((k) => {
              const label = index?.chapters.find((c) => c.category === k)?.category_label ?? k
              return (
                <button
                  key={k}
                  type="button"
                  className={chip(Boolean(value.categories?.includes(k)))}
                  disabled={disabled}
                  onClick={() => toggle('categories', k)}
                >
                  {label}
                </button>
              )
            })}
          </div>
        </div>

        <p className="scope-note">
          限定后走薄服务层的「检索 → 按章节过滤 → 生成」：只把范围内的片段交给模型。
          代价是图谱上下文会被移除（实体/关系在上下文里不带章节归属），所以宽泛问题建议不限定。
          {active && matched === 0 && <b> 当前范围没有命中任何章节，检索会直接拒绝。</b>}
        </p>
      </div>
    </details>
  )
}

/** 只把非空字段传出去，避免给服务层塞一堆空数组。 */
export function toQueryFilter(f: Scope): QueryFilter | null {
  if (!scopeActive(f)) return null
  const out: QueryFilter = {}
  if (f.categories?.length) out.categories = f.categories
  if (f.versions?.length) out.versions = f.versions
  if (f.sources?.length) out.sources = f.sources
  if (f.chapters?.length) out.chapters = f.chapters
  return out
}
