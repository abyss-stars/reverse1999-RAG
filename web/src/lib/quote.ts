/**
 * 「今日台词」。
 *
 * 文案取自**本项目自己的语料**（每话的「副标题」行，全库约 843 条），
 * 由一个本地脚本生成到 public/data/quotes.json —— 该文件**不进仓库**
 * （语料是第三方版权，见 README「版权与许可」）。
 * 生成：python scripts/gen_web_quotes.py
 *
 * 文件缺失时整个模块安静降级：hero 不显示台词，其余功能不受影响。
 */

export interface Quote {
  text: string
  source: string
}

export async function loadQuotes(): Promise<Quote[]> {
  try {
    const res = await fetch('data/quotes.json')
    if (!res.ok) return []
    const data = (await res.json()) as Quote[]
    return Array.isArray(data) ? data.filter((q) => q && typeof q.text === 'string') : []
  } catch {
    return []
  }
}

/** 按「年内第几天」取，因此同一天刷新不变、次日自动换。 */
export function quoteOfDay(quotes: Quote[], date = new Date()): Quote | null {
  if (quotes.length === 0) return null
  const start = Date.UTC(date.getFullYear(), 0, 0)
  const day = Math.floor((date.getTime() - start) / 86_400_000)
  return quotes[day % quotes.length] ?? quotes[0]
}
