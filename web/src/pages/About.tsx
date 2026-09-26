import type { FC } from 'react'
import { CORPUS_LOCK, INDEX_STATS } from '../lib/stats'

/**
 * 合规页。三层声明缺一不可：
 * ① 语料与游戏资源的第三方版权；② 本站性质（个人自用、非官方）；
 * ③ 设计风格的来源与"未复制美术资产"的事实。
 */
export const About: FC<{ chapters: number | null; presetSource: string }> = ({ chapters, presetSource }) => (
  <div>
    <section className="hero compact">
      <div className="wrap">
        <h1>关于与版权</h1>
        <p className="page-sub">这是一个个人自用的剧情检索工具，不是官方站点，也不是公开服务。</p>
      </div>
    </section>

    <div className="wrap">
      <div className="prose" style={{ paddingTop: 20 }}>
      <h2>一、语料与游戏资源</h2>
      <p>
        本站检索的剧情正文来自本地一份第三方整理的《重返未来：1999》简体中文剧情语料
        （锁定 commit <span className="mono">{CORPUS_LOCK}</span>，共 {chapters ?? INDEX_STATS.chapters} 章）。
        语料正文、以及其中涉及的角色、美术、专有名词等游戏资源，<b>版权均归深蓝互动（Bluepoch）所有</b>。
      </p>
      <p>
        本站<b>不提供原文阅读</b>：只展示被检索命中的片段与章节指引，语料原文不随本仓库分发
        （仓库内 <span className="mono">corpus/</span> 被 gitignore 排除）。
      </p>

      <h2>二、本站性质</h2>
      <p>
        本站是<b>个人自用的本地检索工具</b>，<b>非官方</b>，不代表官方立场；
        所有信息以游戏内实际呈现与官方发布为准。索引由本机 LightRAG 构建，
        规模为 {INDEX_STATS.entities.toLocaleString('en-US')} 实体 /{' '}
        {INDEX_STATS.relations.toLocaleString('en-US')} 关系 / {INDEX_STATS.chunks.toLocaleString('en-US')} 文本块。
      </p>

      <h2>三、界面设计</h2>
      <p>
        界面<b>设计风格</b>参考自灰机 wiki《重返未来1999》首页（配色、间距、直角与签名圆角、
        衬线标题的排版语言），但<b>未复制其任何美术资产</b>：
      </p>
      <ol>
        <li>色板与排版参数是对渲染结果<b>逐像素测量</b>得到的（见仓库 <span className="mono">scripts/probe_wiki_palette.py</span>）；</li>
        <li>几何装饰（罗盘、放射线、边角纹样）全部为自绘 SVG；</li>
        <li>未引用该站的图片、图标、字体文件或模板代码；</li>
        <li>
          该站页脚自述「首页图标设计：木头；未经授权禁止用作它用」，本站因此不使用其任何图标。
        </li>
      </ol>
      <p>
        正式上线前，整站背景图将替换为自制素材（当前使用的是本地自备的官方美术，仅用于个人查看）。
      </p>

      <h2>四、检索参数从哪来</h2>
      <p>
        五档检索预设（精确定位 / 专名检索 / 关系链 / 广域扫掠 / 快速应答）的参数由
        <span className="mono">{presetSource}</span> 定义，并经{' '}
        <span className="mono">scripts/preset_matrix.py</span> 实测标定。
        其中一条反直觉结论：<b>覆盖广度的瓶颈是 <span className="mono">max_total_tokens</span> 而不是{' '}
        <span className="mono">chunk_top_k</span></b>——单独把 chunk_top_k 从 120 调到 200，覆盖反而从 38 章掉到 19 章。
      </p>

      <h2>五、技术栈</h2>
      <p>
        前端 React + Vite + TypeScript，手写 CSS 设计令牌（不用 UI 框架，换肤只改一个
        <span className="mono"> :root</span> 块）；检索与生成由本机 LightRAG 提供
        （PostgreSQL + pgvector 四件套存储）。答案由大模型生成，<b>可能出错</b>，
        请以引用到的章节原文为准。
      </p>
      </div>
    </div>
  </div>
)
