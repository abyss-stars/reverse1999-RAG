/**
 * 把模型输出的「思考块」从答案正文里剥出来。
 *
 * 为什么需要：本项目**故意**给回答角色保留思考（AGENTS.md §2.7 —— 抽取/关键词角色关掉
 * thinking 是为了省钱，回答角色保留是为了质量）。但实测该模型把思维链**内联**在
 * content 流里、用 `<think>…</think>` 包起来，于是它会直接显示给用户。
 * 端到端验证时抓到：正文开头是 `<think>We need answer in Chinese…`。
 *
 * 处理策略：思考内容不丢（它有时对核对引用有用），但**折叠**起来、默认不显示，
 * 且不参与"是否有可靠依据"的判断。
 */

const OPEN_RE = /<think(?:ing)?>/i
const CLOSE_RE = /<\/think(?:ing)?>/i

export interface SplitResult {
  /** 思考过程（无则 null）。流式过程中可能只有半截。 */
  thinking: string | null
  /** 真正的答案正文 */
  answer: string
  /** 流还没结束、思考块尚未闭合 */
  thinkingOpen: boolean
}

export function splitThinking(raw: string): SplitResult {
  const open = OPEN_RE.exec(raw)
  if (!open) return { thinking: null, answer: raw, thinkingOpen: false }

  const afterOpen = raw.slice(open.index + open[0].length)
  const close = CLOSE_RE.exec(afterOpen)

  if (!close) {
    // 还在思考：正文视为空，思考内容先暂存
    return {
      thinking: afterOpen.trim() || null,
      answer: raw.slice(0, open.index).trim(),
      thinkingOpen: true,
    }
  }

  const thinking = afterOpen.slice(0, close.index).trim()
  const answer = (raw.slice(0, open.index) + afterOpen.slice(close.index + close[0].length)).trim()
  return { thinking: thinking || null, answer, thinkingOpen: false }
}
