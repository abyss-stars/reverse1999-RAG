import type { FC } from 'react'
import { MarkIcon } from './Icons'
import { navigate } from '../lib/hashRoute'
import type { Route } from '../lib/hashRoute'

export const Strip: FC<{ chapters: number | null; chunks: number | null }> = ({ chapters, chunks }) => (
  <div className="strip">
    <div className="wrap">
      <span className="brand-en en">Reverse: 1999 · Story Archive</span>
      <span className="src">
        数据来源：本地 LightRAG 索引
        {chapters !== null && (
          <>
            {' · '}
            <b>{chapters}</b> 章
          </>
        )}
        {chunks !== null && (
          <>
            {' · '}
            <b>{chunks.toLocaleString('en-US')}</b> 文本块
          </>
        )}
      </span>
    </div>
  </div>
)

const NAV: Array<{ name: Route['name']; href: string; label: string }> = [
  { name: 'home', href: '/', label: '检索' },
  { name: 'chapters', href: '/chapters', label: '章节档案' },
  { name: 'about', href: '/about', label: '关于' },
]

export const TopBar: FC<{ current: Route['name'] }> = ({ current }) => (
  <header className="topbar">
    <div className="wrap">
      <MarkIcon className="mark" />
      <span className="site-name">1999 剧情档案</span>
      <span className="site-sub en">Story Archive</span>
      <nav className="topnav">
        {NAV.map((n) => (
          <a
            key={n.name}
            href={`#${n.href}`}
            aria-current={current === n.name ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault()
              navigate(n.href)
            }}
          >
            {n.label}
          </a>
        ))}
      </nav>
    </div>
  </header>
)

export const Footer: FC<{ chapters: number | null; chunks: number | null; build: string }> = ({
  chapters,
  chunks,
  build,
}) => (
  <footer className="site">
    <div className="wrap">
      <div className="foot-stats">
        <div>
          <div className="n">{chapters ?? '—'}</div>
          <div className="l">剧情章节</div>
        </div>
        <div>
          <div className="n">{chunks !== null ? chunks.toLocaleString('en-US') : '—'}</div>
          <div className="l">文本块</div>
        </div>
        <div>
          <div className="n">10/10</div>
          <div className="l">回归通过</div>
        </div>
      </div>

      <div className="foot-cols">
        <div>
          <h4>本工具</h4>
          <ul>
            <li>五档检索预设</li>
            <li>章节档案与版本</li>
            <li>引用可追溯</li>
          </ul>
        </div>
        <div>
          <h4>数据来源</h4>
          <ul>
            <li>本地 LightRAG 索引</li>
            <li>PostgreSQL + pgvector</li>
            <li>语料锁定 f6e18439</li>
          </ul>
        </div>
        <div>
          <h4>声明</h4>
          <ul>
            <li>非官方 · 个人自用</li>
            <li>游戏资源版权归深蓝互动</li>
            <li>设计风格致敬灰机 wiki</li>
          </ul>
        </div>
      </div>

      <div className="legal">
        <b>版权与免责。</b>本站为个人自用的剧情检索工具，<b>非官方站点</b>，不代表官方立场。
        语料正文与其中涉及的游戏资源（角色、美术、术语）版权归 <b>深蓝互动</b> 所有，本站仅用于本地检索与呈现。
        界面设计风格参考自灰机 wiki《重返未来1999》首页，但<b>未复制其任何美术资产</b>
        （首页图标等由该站作者持有并声明禁止他用）。正式上线前，整站背景将替换为自制素材。
        <br />
        <span className="mono">build {build}</span>
      </div>
    </div>
  </footer>
)
