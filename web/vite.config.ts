import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * 开发期拓扑（开发期形态：L3b）：
 *   浏览器 → Vite dev (:5173) ──/api/*──▶ 薄服务层 (:8787) ──▶ LightRAG (:9621)
 *
 * 薄服务层承载"版本/章节过滤"（检索 → 过滤 → 生成）与预设下发；
 * 不设过滤时它把请求原样透传给 LightRAG。
 *
 * 全程**同源**（前端只请求自己的 /api），因此不依赖 CORS ——
 * 虽然实测后端默认 `CORS_ORIGINS=*` 直连也能通，
 * 但同源才是上线形态的真实行为。
 *
 * `base: './'` + 相对资源路径：产物可以挂在任意前缀下（`/workspace/`、`/site01/workspace/`）。
 */
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    // 首屏预算守卫（对标上游 lightrag_webui 的做法，但阈值按本项目定）
    chunkSizeWarningLimit: 400,
  },
  server: {
    port: 5173,
    proxy: {
      // 薄服务层（L3b）—— 默认走它，它自己再转发给 LightRAG
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: true,
      },
      // 直连 LightRAG 的应急通道：把 VITE_API_BASE 设成 /lightrag 时用它
      '/lightrag': {
        target: 'http://localhost:9621',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/lightrag/, ''),
      },
    },
  },
})
