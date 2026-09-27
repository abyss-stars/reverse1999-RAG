import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/app.css'
import App from './App'

/** 背景图文件名（放在 `public/bg/` 下）。换图只改这一处。 */
const BG_FILE = 'bg/1999.webp'

/**
 * 整站背景图：**必须先解析成绝对 URL** 再写进自定义属性。
 *
 * 坑：自定义属性里的相对 `url()` 不按「声明它的地方」解析，而按
 * **用到它的那条声明所在的样式表**解析。`app.css` 消费 `var(--bg-img)`，
 * 产物里那张样式表在 `/assets/` 下，于是 `./bg/1999.webp` 会被解析成
 * `/assets/bg/1999.webp` → 404（图其实在 `/bg/1999.webp`）。
 *
 * 这个坑只在**产物**里暴露：dev 下 `BASE_URL` 是 `/`，拼出来恰好是绝对路径。
 * `base: './'` 造成的 dev/产物行为差异，详见 `vite.config.ts`。
 *
 * 图与 `index.html` 同级（`public/bg/` 会被拷到产物根），故按 `document.baseURI`
 * 解析 —— 挂在 `/workspace/` 这类前缀下也依然正确。
 * 图不在仓库里（第三方美术），缺失时退化为纯色画布，不报错。
 */
document.documentElement.style.setProperty(
  '--bg-img',
  `url("${new URL(BG_FILE, document.baseURI).href}")`,
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
