/**
 * 章节元数据。数据来自 state/chapter_index.json（构建时拷进 public/data/），
 * 它由 pipeline 侧生成，是"81 章的 order/章号/标题/分类/版本 + 版本来源"的真源。
 */

export interface ChapterRecord {
  order: number
  chapter_no: string
  title: string
  category: string
  category_label: string
  source_rel: string
  filename: string
  episodes: number
  trails: number
  exists: boolean
  bytes: number
  ordinal?: string | null
  version: string | null
  version_source: string | null
}

export interface ChapterIndex {
  format: string
  counts: Record<string, number>
  total: number
  chapters: ChapterRecord[]
}

/** 版本来源的可信度注解。 */
export const VERSION_SOURCE_NOTE: Record<string, string> = {
  metadata: '游戏自身导出字段，最权威',
  wiki: '灰机 wiki 逐章实测，三方互证',
  number_rule: '章节号前两位规则；活动已验证，角色/轶事置信度较低',
  null: '无任何来源，未猜',
}

export const CATEGORY_ORDER = ['mainline', 'activity', 'character', 'anecdote'] as const

export function categoryLabel(idx: ChapterIndex, key: string): string {
  return idx.chapters.find((c) => c.category === key)?.category_label ?? key
}

/** `101-在我们的时代里.md` → 与 chapter_index 的 filename 对齐。 */
export function fileBase(filePath: string): string {
  const noDir = filePath.replace(/\\/g, '/').split('/').pop() ?? filePath
  return noDir.trim()
}

export function buildFileMap(idx: ChapterIndex): Map<string, ChapterRecord> {
  const m = new Map<string, ChapterRecord>()
  for (const c of idx.chapters) m.set(c.filename, c)
  return m
}

/**
 * 拿 references[].file_path 回查章节。
 * LightRAG 返回的 file_path 就是上传时的文件名，所以直接按 filename 命中；
 * 万一带了目录前缀，退一步用 basename 再试一次。
 */
export function chapterForPath(map: Map<string, ChapterRecord>, filePath: string): ChapterRecord | undefined {
  const base = fileBase(filePath)
  return map.get(base) ?? map.get(decodeURIComponent(base))
}

/** 用章节信息拼一个"就这一章提问"的问题（供引用卡/章节卡跳转问答页用）。 */
export function questionForChapter(c: ChapterRecord): string {
  return `《${c.title}》（${c.chapter_no}）讲了什么？`
}

export async function loadChapterIndex(): Promise<ChapterIndex> {
  const res = await fetch('data/chapter_index.json')
  if (!res.ok) throw new Error(`chapter_index.json 读取失败：HTTP ${res.status}`)
  return (await res.json()) as ChapterIndex
}

/** 与薄服务层 `FilterSpec.match` 保持一致，用于前端即时显示"命中多少章"。 */
export interface ScopeFilter {
  categories?: string[]
  versions?: string[]
  sources?: string[]
  chapters?: string[]
  min_order?: number | null
  max_order?: number | null
}

export function scopeActive(f: ScopeFilter | null | undefined): boolean {
  if (!f) return false
  return Boolean(
    f.categories?.length ||
      f.versions?.length ||
      f.sources?.length ||
      f.chapters?.length ||
      f.min_order != null ||
      f.max_order != null,
  )
}

export function matchChapter(c: ChapterRecord, f: ScopeFilter): boolean {
  if (f.categories?.length && !f.categories.includes(c.category)) return false
  if (f.versions?.length && !f.versions.includes(c.version ?? '')) return false
  if (f.sources?.length && !f.sources.includes(c.version_source ?? 'null')) return false
  if (f.chapters?.length && !f.chapters.includes(String(c.chapter_no))) return false
  if (f.min_order != null && c.order < f.min_order) return false
  if (f.max_order != null && c.order > f.max_order) return false
  return true
}

export function countMatching(index: ChapterIndex | null, f: ScopeFilter): number {
  if (!index) return 0
  if (!scopeActive(f)) return index.chapters.length
  return index.chapters.filter((c) => matchChapter(c, f)).length
}

/** 把范围描述成一句话，用于 UI 摘要与后端提示。 */
export function describeScope(f: ScopeFilter): string {
  if (!scopeActive(f)) return '全部章节'
  const parts: string[] = []
  if (f.categories?.length) parts.push('分类 ' + f.categories.join('/'))
  if (f.versions?.length) parts.push('版本 ' + f.versions.join('/'))
  if (f.sources?.length) parts.push('来源 ' + f.sources.join('/'))
  if (f.chapters?.length) parts.push('章号 ' + f.chapters.join('/'))
  return parts.join(' · ')
}
