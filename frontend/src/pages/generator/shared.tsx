import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { FieldIssue, FormatsResponse, Verification } from '../../api/generator'
import { cx } from '../../lib/format'

export function useFormats() {
  return useQuery({
    queryKey: ['generator', 'formats'],
    queryFn: () => api<FormatsResponse>('/api/generator/formats/'),
    staleTime: Infinity,
  })
}

const VERDICT: Record<Verification, { label: string; className: string }> = {
  PASS: { label: 'Pass', className: 'bg-[#EAF6F0] text-pass border-[#BFE3D3]' },
  FAIL: { label: 'Fail', className: 'bg-[#FCEEEF] text-fail border-[#F1C4C7]' },
  UNAVAILABLE: { label: 'Not checked', className: 'bg-canvas text-muted border-rule' },
}

export function VerificationBadge({ status }: { status: Verification }) {
  const v = VERDICT[status]
  return <span className={cx('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium', v.className)}>{v.label}</span>
}

export function issuesFor(issues: FieldIssue[] | undefined, field: string): string[] {
  return (issues ?? []).filter((i) => i.field === field).map((i) => i.message)
}

export function FieldMessages({ errors, warnings, id }: { errors: string[]; warnings?: string[]; id?: string }) {
  if (!errors.length && !warnings?.length) return null
  return (
    <div id={id} className="mt-1.5 space-y-1">
      {errors.map((m) => <p key={m} className="text-xs text-fail">{m}</p>)}
      {warnings?.map((m) => <p key={m} className="text-xs text-review">{m}</p>)}
    </div>
  )
}

export const inputClass =
  'block w-full rounded-md border border-rule bg-paper px-3 text-sm focus:border-electric focus:outline-none aria-[invalid=true]:border-fail'

export function Field({ id, label, hint, children }: { id: string; label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
    </div>
  )
}

export function DownloadLinks({ links, compact = false }: { links: Record<string, string>; compact?: boolean }) {
  const names: Record<string, string> = { png: 'PNG', svg: 'SVG', pdf: 'Print label (PDF)', zip: 'All files (ZIP)', csv: 'Report (CSV)' }
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(links).map(([kind, href]) => (
        <a key={kind} href={href} download
          className={cx('inline-flex items-center rounded-md border border-rule bg-paper font-medium text-ink hover:bg-canvas',
            compact ? 'h-7 px-2 text-xs' : 'h-9 px-3.5 text-sm')}>
          {compact && kind === 'pdf' ? 'PDF' : names[kind] ?? kind.toUpperCase()}
        </a>
      ))}
    </div>
  )
}
