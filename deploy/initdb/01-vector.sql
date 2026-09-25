-- ============================================================
--  1999RAG · PostgreSQL 初始化
--  仅在 ./data/pgdata 为空的首次启动时执行
-- ============================================================

-- LightRAG 的 PGVectorStorage 需要 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 便于排查: 打印版本
DO $$
BEGIN
    RAISE NOTICE 'pgvector version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
    RAISE NOTICE 'server version: %', version();
END $$;
