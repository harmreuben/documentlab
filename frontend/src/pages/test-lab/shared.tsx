import type { Change, Outcome } from '../../api/testlab'
import { cx } from '../../lib/format'

const OUTCOME: Record<Outcome, { label: string; className: string }> = {
  PASS: { label: 'Passed', className: 'bg-[#EAF6F0] text-pass border-[#BFE3D3]' },
  FAIL: { label: 'Failed', className: 'bg-[#FCEEEF] text-fail border-[#F1C4C7]' },
  ERROR: { label: 'Error', className: 'bg-ink text-white border-ink' },
}

/** A test's outcome: did DocumentLab do what the fixture expected? (Not the document's own result.) */
export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const o = OUTCOME[outcome]
  return <span className={cx('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap', o.className)}>{o.label}</span>
}

const CHANGE: Partial<Record<Change, { label: string; className: string }>> = {
  new_failure: { label: 'New failure', className: 'text-fail' },
  fixed: { label: 'Fixed', className: 'text-pass' },
  still_failing: { label: 'Still failing', className: 'text-muted' },
  new: { label: 'New', className: 'text-faint' },
}

export function ChangeLabel({ change }: { change: Change }) {
  const c = CHANGE[change]
  return c ? <span className={cx('text-xs font-medium whitespace-nowrap', c.className)}>{c.label}</span> : null
}
