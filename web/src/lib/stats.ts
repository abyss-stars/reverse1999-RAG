/**
 * 索引规模。数字来源：2026-09-26 的 `state/index_manifest.json` 与 PostgreSQL 直查
 * （见 `next.md` §1）。**索引重建后需要更新**；后续应由薄服务层提供实时值。
 * `chapters` 在运行时用真实的 chapter_index.json 长度覆盖，所以这里写不写不太要紧。
 */
export const INDEX_STATS = {
  chapters: 81,
  entities: 9896,
  relations: 16737,
  chunks: 2439,
  cache: 8726,
} as const

/** 语料锁（state/corpus.lock.json）。 */
export const CORPUS_LOCK = 'f6e18439'
