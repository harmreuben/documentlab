import type { ResultStatus } from '../api/analyzer'
import { cx } from '../lib/format'

/** The six result statuses used everywhere in DocumentLab, worded for people. */
export const STATUS: Record<ResultStatus, { label: string; badge: string; stroke: string }> = {
  PASS: { label: 'Pass', badge: 'bg-[#EAF6F0] text-pass border-[#BFE3D3]', stroke: '#0F8A5F' },
  FAIL: { label: 'Fail', badge: 'bg-[#FCEEEF] text-fail border-[#F1C4C7]', stroke: '#C2343B' },
  REVIEW_REQUIRED: { label: 'Needs review', badge: 'bg-[#FFF4E5] text-review border-[#F3D5A8]', stroke: '#A86200' },
  NOT_SUPPORTED: { label: 'Not supported', badge: 'bg-canvas text-muted border-rule', stroke: '#5B6678' },
  UNAVAILABLE: { label: 'Unavailable', badge: 'bg-canvas text-muted border-rule', stroke: '#5B6678' },
  NOT_CHECKED: { label: 'Not checked', badge: 'bg-paper text-faint border-rule', stroke: '#8A94A6' },
}

export function StatusBadge({ status, large = false }: { status: ResultStatus; large?: boolean }) {
  const s = STATUS[status]
  return (
    <span className={cx('inline-flex items-center rounded-full border font-medium whitespace-nowrap', s.badge,
      large ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs')}>
      {s.label}
    </span>
  )
}
