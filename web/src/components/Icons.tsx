import type { FC } from 'react'

interface IconProps {
  className?: string
}

/** 站点标记 —— 自绘几何图形，不是参考站的 Logo。 */
export const MarkIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
    <path d="M16 3 29 16 16 29 3 16Z" />
    <path d="M16 8.5 23.5 16 16 23.5 8.5 16Z" opacity={0.55} />
    <path d="M16 3v26M3 16h26" opacity={0.3} />
    <circle cx="16" cy="16" r="2.4" fill="currentColor" stroke="none" />
  </svg>
)

export const SearchIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden="true">
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4.5 4.5" />
  </svg>
)

const PinpointIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
    <circle cx="16" cy="16" r="10" />
    <circle cx="16" cy="16" r="4" />
    <path d="M16 2v4M16 26v4M2 16h4M26 16h4" />
  </svg>
)

const LookupIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
    <path d="M6 5h13a3 3 0 0 1 3 3v19H9a3 3 0 0 1-3-3Z" />
    <path d="M22 8h4v19H12" />
    <path d="M11 12h7M11 17h7" />
  </svg>
)

const ChainIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
    <path d="M11 16h10" />
    <path d="M6 12l5 4-5 4ZM26 12l-5 4 5 4Z" />
    <circle cx="16" cy="16" r="2" />
  </svg>
)

const SweepIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
    <path d="M4 26h24" />
    <path d="M6 26 14 6M12 26 18 6M18 26 22 6M24 26 26 6" />
  </svg>
)

const QuickIcon: FC<IconProps> = ({ className }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
    <path d="M17 3 7 18h7l-1 11 11-16h-7Z" />
  </svg>
)

const PRESET_ICONS: Record<string, FC<IconProps>> = {
  pinpoint: PinpointIcon,
  lookup: LookupIcon,
  chain: ChainIcon,
  sweep: SweepIcon,
  quick: QuickIcon,
}

export const PresetIcon: FC<IconProps & { name: string }> = ({ name, className }) => {
  const Cmp = PRESET_ICONS[name] ?? PinpointIcon
  return <Cmp className={className} />
}
