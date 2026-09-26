import type { FC } from 'react'
import { PRESETS } from '../api/presets'
import { PresetIcon } from './Icons'

/**
 * 五档预设瓦片。技法来自参考站的 `.mp-btn`：直角、#111 底、9px 黑晕、
 * 悬停转 #333、英文标签竖排 90°。下方指示条复用它的轮播指示条母题（2px / 激活 4px）。
 */
export const PresetGrid: FC<{
  value: string
  onChange: (name: string) => void
  disabled?: boolean
}> = ({ value, onChange, disabled }) => {
  const activeIndex = Math.max(
    0,
    PRESETS.findIndex((p) => p.name === value),
  )

  return (
    <section className="presets">
      <div className="sec-head">
        <h2>检索档位</h2>
        <span className="en">Retrieval Presets</span>
        <span>· 选一个再提问；不确定就用「精确定位」</span>
      </div>

      <div className="preset-grid" role="group" aria-label="检索档位">
        {PRESETS.map((p) => (
          <button
            key={p.name}
            type="button"
            className="preset"
            aria-pressed={value === p.name}
            disabled={disabled}
            title={p.when}
            onClick={() => onChange(p.name)}
          >
            <span className="en-tag">{p.name}</span>
            <PresetIcon name={p.name} className="ico" />
            <span className="label">{p.label}</span>
            <span className="sum">{p.summary}</span>
            <span className="meta">
              {p.mode} · 检索 <b>{p.latency}</b> · 花费 <b>{p.cost}</b>
            </span>
          </button>
        ))}
      </div>

      <div className="bars" aria-hidden="true">
        {PRESETS.map((p, i) => (
          <i key={p.name} className={i === activeIndex ? 'on' : undefined} />
        ))}
      </div>
    </section>
  )
}
