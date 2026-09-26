import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/app.css'
import App from './App'

/**
 * 整站背景图用 `BASE_URL` 拼相对路径：产物挂到 `/workspace/` 或
 * `/site01/workspace/` 下都能找对（`base: './'`）。
 * 图不在仓库里（第三方美术，见 website.md C-8b），缺失时退化为纯色画布，不报错。
 */
const base = import.meta.env.BASE_URL || '/'
document.documentElement.style.setProperty('--bg-img', `url("${base}bg/1999.jpg")`)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
