# web/ — 1999 剧情档案（L3 前端工程）

React + Vite + TypeScript，**手写 CSS 设计令牌**（不用 UI 框架）。
视觉与版式来自 `web/design/v0-home.html` 的定稿。

---

## 快速开始

**要起两个进程**（前端 + 薄服务层），另加 LightRAG 后端：

```powershell
# ① LightRAG 后端（:9621）
.\scripts\up.ps1

# ② 薄服务层（:8787）—— 仓库根目录，用 server/.venv 的 Python
server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8787

# ③ 前端（:5173）
cd web
npm install
npm run dev
```

开发期拓扑（全链路同源，不依赖 CORS）：

```
浏览器 → Vite :5173 ──/api/*──▶ 薄服务层 :8787 ──▶ LightRAG :9621
```

`/api` 由 `vite.config.ts` 代理到 :8787。不想要薄服务层时，把 `VITE_API_BASE=/lightrag`
即可绕过它直连 LightRAG（应急通道；代价是没有版本过滤与预设下发）。

必须先有的两个本地数据（都不进仓库）：

| 文件 | 生成方式 | 缺失时 |
|---|---|---|
| `public/bg/1999.jpg` | 手工放入（官方美术，仅本地自用） | 背景退化为纯色画布，功能不受影响 |
| `public/data/quotes.json` | `python scripts/gen_web_quotes.py` | hero 不显示今日台词 |

`public/data/chapter_index.json` 已随仓库提供（来自 `state/chapter_index.json`），
索引重建后需要重新拷贝；若接了薄服务层，也可以改从 `/api/chapters` 取。

其他命令：

```powershell
npm run typecheck    # tsc --noEmit（CI 该跑这个）
npm run build        # 产物在 dist/（薄服务层会自动托管它，见 server/README.md）
npm run preview      # 预览构建产物
```

---

## 端到端验证（不是"我觉得能跑"）

```powershell
node scripts/verify-app.mjs
node scripts/verify-app.mjs --question "阿尔卡纳是谁？" --preset chain
```

它真起一个 headless Edge，用 CDP 打开「带问题的分享链接」，**轮询 DOM 直到回答落地**，
再断言并截图到 `docs/ref/app-e2e.png`：

```
[PASS] 流程走完（readout 出现）
[PASS] 拿到答案正文
[PASS] 答案里含引用角标
[PASS] 引用面板有卡片
[PASS] 默认最多展示 4 条引用卡
[PASS] 引用卡解析出了章节信息
[PASS] 未被判为无依据
[PASS] 点击 N 个 >4 的角标，全部被提升为可见   ← 仅在正文有 >4 角标时出现
[PASS] 无横向溢出（窗口px, scrollWidth … ≤ …）
```

> **"角标提升"那条是按需出现的**：`pinpoint` 的默认问题正文只有 1 个角标，
> 测不到这条路径，脚本会明确打印「跳过」而不是假装通过。
> 要真正压到它，用宽泛问题 + `sweep`：
>
> ```powershell
> node scripts/verify-app.mjs --question "「暴雨」到底是什么？它对世界有什么影响？" --preset sweep
> ```
>
> 这样正文会有 20+ 个角标，脚本一次点最多 5 个 >4 的并逐个断言。

> 为什么不直接 `edge --screenshot`：那样要靠 `--virtual-time-budget` 等页面跑完，
> 而虚拟时钟会被我们的 `setInterval` 计时器瞬间烧完，截图永远停在流式中途。
> CDP 轮询是唯一能"等到回答落地"的可靠做法。
>
> ⚠️ 但也正是 `Page.captureScreenshot`（整页截图）会**阻塞渲染进程**，
> 把 React 的 passive effect 冲刷推迟 —— 见下面 ⑤ 那个真 bug。

---

## 目录结构

```
src/
  api/
    types.ts        与 LightRAG 端点对齐的类型
    presets.ts      ⚠️ 生成文件，别手改 —— 由 query_planner.py 生成
    client.ts       /query/stream 的 NDJSON 客户端 + apiBase()
  components/
    Chrome.tsx      Strip / TopBar / Footer
    Hero.tsx        大标题 + 日期块 + 今日台词 + 索引概况卡
    PresetGrid.tsx  五档预设瓦片
    AnswerPanel.tsx 状态行 + 答案卡 + 引用面板
    Icons.tsx       自绘 SVG（不引用参考站任何图标）
  hooks/useQueryRunner.ts   流式状态机（阶段/增量/中止/计时）
  lib/
    chapter.ts      chapter_index.json 加载 + file_path 回查章节
    miniMarkdown.tsx 极简 Markdown 渲染（构造 React 元素，无 innerHTML）
    think.ts        剥离模型内联的 <think> 思考块
    hashRoute.ts    极简 hash 路由（见下）
    quote.ts        今日台词
    stats.ts        索引规模常量
  pages/            Home / Chapters / About
  styles/
    tokens.css      ★ 设计令牌 —— 换肤只改这一个文件
    app.css         版式与组件
scripts/
  verify-app.mjs    CDP 端到端验证
```

---

## 几个"为什么这么做"的决定

**① hash 路由而不是 react-router。**
上线形态是把产物交给**薄服务层**用 `StaticFiles` 托管（`server/app.py` 末尾的挂载；
L3b 下前端要调本服务的 `/api/*`，所以挂进 LightRAG 容器是错的）——
而 `StaticFiles` **没有 SPA fallback**，`/chapters` 这种真实路径一刷新就 404。hash 路由天然免疫，
还少一个依赖。副作用：把「问题 + 档位」写进 hash 后**分享链接天然可用**
（`#/?q=…&preset=sweep`），这正是原生 `/workspace` 做不到的那件事。

**② 设计令牌集中在 `tokens.css`。**
验收标准之一是"换肤只需改一处"。色板、字体、签名圆角、遮罩倍数、hero 高度
全部是 `:root` 变量；组件 CSS 一律只引用变量，不写字面色值。

**③ 遮罩曲线按页切换**（`body[data-page]`）。
首页那条曲线把"透气窗"留在 380px（hero 高 470px），480px 之后才压实。
而 `/chapters`、`/about` 没有整屏 hero，正文从 ~200px 就开始 ——
**实测第一版它们正好落在背景最亮的窗口里，提示行几乎读不出来**。
所以这两页换一条把压实提前的曲线，并把页头放进 18vh 的紧凑 hero。

**④ 思考块必须剥掉再渲染。**
本项目**故意**给回答角色保留思考（抽取/关键词角色关掉 thinking 是为了省钱，
回答角色保留是为了质量）。但实测该模型把思维链**内联**在 content 流里、
用 `<think>…</think>` 包起来 —— 端到端验证时抓到正文开头是
`<think>We need answer in Chinese…`。现在 `lib/think.ts` 把它剥出来折叠显示，
且**不参与"是否有可靠依据"的判断**（否则思维链里的引用字样会把空回答误判成 grounded）。

**⑤ 引用面板默认只显示 4 条，并支持「点角标临时提升」。**
`pinpoint` 档一次常命中 20+ 章，全展开会把页面拉到 6000px 以上，
而英雄区之下第一屏正好能完整放下 4 张卡。标题会写成 `引用（4 / 21）`，
并保留「展开全部」按钮，两种读法都给你。

> **为什么不只是"截断到 4 条"**：答案正文里可能写着 `[21]`，
> 而卡片默认不存在 —— 点角标就**毫无反应**，正文列了出处、界面上却找不到。
> 所以 `visibleRefs` = 前 4 条 **∪** 被角标点开过的那些（保持检索原序）。

> **这里抓到一个真 bug，值得记**：第一版在 `running` 由 true 变 false（流结束）时
> 无条件清空"提升"状态。看起来对，但 E2E 偶发失败：答案落地后立刻点角标，
> 提升被 completion 那次重置抹掉了。根因是 `Page.captureScreenshot`
> （整页截图，正文 1.4 万字时很慢）**阻塞渲染进程，把 React 的 passive effect
> 冲刷推迟到了点击之后**。修法是只在「新一轮**开始**」时清状态（用 `prevRun` ref
> 判上升沿），不在结束时清 —— 顺带修掉了"流式过程中展开引用、
> 答案一落地就被自动收起"这个真实可见的问题。
>
> 教训：**探针的读数本身也要被怀疑**。中途我以为是
> `Boolean(getElementById(...))` 读不到 DOM 节点（CDP `returnByValue` 对 DOM 节点
> 返回 `{}`），专门写了个最小实验证明它是对的（存在→`{}`→true，不存在→`null`→false），
> 才发现方向在代码里。

---

## 已知未做（下一步）

| 项 | 说明 |
|---|---|
| ~~薄服务层（L3b 的另一半）~~ | ✅ 已完成（`server/`）。问答页的「检索范围」就是它的前端入口 |
| **KG 按章节过滤** | 启用范围限定时**整段丢弃图谱上下文**（实体/关系行不带来源字段）。彻底方案需按 DB 的 `lightrag_entity_chunks` 反查，见 `server/README.md` |
| 移动端引用抽屉 | 窄屏目前纵向堆叠（390px 无横向溢出已验证，抽屉未做） |
| 索引规模实时化 | 薄服务层 `/api/stats` 已能实时给值，`lib/stats.ts` 还是常量 |
| ScopeFilter 里选章号 | 目前只能从章节页带 `ch=章号` 过来；问答页不能手选章号 |
| 首屏体积守卫 | `vite.config.ts` 里设了 `chunkSizeWarningLimit`，但没像上游那样做硬性 baseline 守卫 |

---

## 检索范围限定（薄服务层的前端入口）

问答页「检索档位」下方有一个可折叠的 **检索范围**：

- 选**版本**（1.0~4.0）与/或**分类**（主线/活动/角色/轶事）→ 走薄服务层的「检索 → 按章节过滤 → 生成」
- 摘要行即时显示「命中 N / 81 章」，命中 0 章时服务层会**直接拒绝**而不是硬编答案
- 答案上方会出现**回报条**：`已限定检索范围 版本=1.0 上下文片段 25 → 3 · 引用 21 → 3`
- 范围会写进 hash（`#/?q=…&preset=…&ver=1.0`），所以**分享链接能带着范围走**
- 章节档案页的「就这一章提问」会把 `ch=章号` 带过来，形成单章检索

代价（UI 里已明示）：**图谱上下文会被移除**，所以宽泛问题建议不限定。
