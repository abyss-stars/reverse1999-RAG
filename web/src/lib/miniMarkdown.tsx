import type { ReactNode } from 'react'

/**
 * 极简 Markdown 渲染 —— 只覆盖 LightRAG 答案实际用到的语法：
 * `#`/`##`/`###` 标题、`-`/`*` 列表、`**粗体**`、段落，以及 `[n]` 引用角标。
 *
 * 为什么不用 marked：① 少一个依赖；② **全程构造 React 元素而不是 innerHTML**，
 * 天然没有 XSS 面；③ 引用角标需要变成可点按钮，交给通用解析器反而更绕。
 */
export function renderAnswer(
  text: string,
  onCite: (n: number) => void,
  activeCite: number | null,
  keyPrefix = 'a',
): ReactNode[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const out: ReactNode[] = []
  let paragraph: string[] = []
  let list: string[] = []
  let k = 0

  const flushParagraph = () => {
    if (paragraph.length === 0) return
    const joined = paragraph.join(' ')
    out.push(<p key={`${keyPrefix}-p${k++}`}>{inline(joined, onCite, activeCite, `${keyPrefix}-p${k}`)}</p>)
    paragraph = []
  }
  const flushList = () => {
    if (list.length === 0) return
    out.push(
      <ul key={`${keyPrefix}-ul${k++}`} style={{ margin: '0 0 14px', paddingLeft: 20 }}>
        {list.map((item, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            {inline(item, onCite, activeCite, `${keyPrefix}-l${k}-${i}`)}
          </li>
        ))}
      </ul>,
    )
    list = []
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (!line.trim()) {
      flushParagraph()
      flushList()
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      flushParagraph()
      flushList()
      const level = h[1].length
      const body = inline(h[2], onCite, activeCite, `${keyPrefix}-h${k}`)
      out.push(
        <p
          key={`${keyPrefix}-h${k++}`}
          style={{
            fontFamily: 'var(--serif)',
            fontSize: level <= 2 ? 17 : 15,
            color: 'var(--cream)',
            margin: '18px 0 8px',
            fontWeight: 700,
          }}
        >
          {body}
        </p>,
      )
      continue
    }
    const li = /^[-*]\s+(.*)$/.exec(line)
    if (li) {
      flushParagraph()
      list.push(li[1])
      continue
    }
    // 表格行 / 分隔线等暂不支持：原样当段落，避免丢内容。
    flushList()
    paragraph.push(line.trim())
  }
  flushParagraph()
  flushList()
  return out
}

/** 行内：`**粗体**` 与 `[n]` 引用角标。 */
function inline(text: string, onCite: (n: number) => void, active: number | null, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*)|(\[\d+\])/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    if (m[1]) {
      nodes.push(<strong key={`${keyPrefix}-b${i++}`}>{m[1].slice(2, -2)}</strong>)
    } else if (m[2]) {
      const n = Number(m[2].slice(1, -1))
      nodes.push(
        <button
          key={`${keyPrefix}-c${i++}`}
          type="button"
          className="cite"
          aria-label={`跳转到引用 ${n}`}
          aria-pressed={active === n}
          onClick={() => onCite(n)}
        >
          {n}
        </button>,
      )
    }
    last = m.index + m[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}
