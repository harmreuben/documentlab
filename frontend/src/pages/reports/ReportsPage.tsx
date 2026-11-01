import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { STATUS } from '../../components/StatusBadge'
import { Loading, Notice, PageHeader, Panel } from '../../components/ui'
import { inputClass } from '../generator/shared'

interface Section { label: string; total: number; by_status: Record<string, number>; reviews?: Record<string, number> }
interface Summary {
  start: string; end: string; scope: 'everyone' | 'own'; ruleset_version: string; app_version: string
  sections: { analyzer: Section; documents?: Section; ssn?: Section
    test_lab: { label: string; runs: number; runs_with_failures: number; last_run: { reference: string; passed: number; total: number } | null } }
  rules: { code: string; name: string; module: string; failed: number; review: number }[]
}

const REVIEW_WORDS: Record<string, string> = { PENDING: 'Waiting', CONFIRMED: 'Confirmed', REJECTED: 'Rejected', EXPIRED: 'Data deleted first' }
const ORDER = ['PASS', 'REVIEW_REQUIRED', 'FAIL', 'NOT_SUPPORTED', 'UNAVAILABLE', 'NOT_CHECKED']

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function ReportsPage() {
  const { user } = useAuth()
  const [end, setEnd] = useState(() => iso(new Date()))
  const [start, setStart] = useState(() => {
    const today = new Date()
    return iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29))
  })
  const query = `start=${start}&end=${end}`
  const summary = useQuery({ queryKey: ['reports', 'summary', start, end], queryFn: () => api<Summary>(`/api/reports/summary/?${query}`),
    enabled: !!start && !!end })
  const identity = user && ['ADMINISTRATOR', 'ANALYST', 'REVIEWER'].includes(user.role)

  return (
    <>
      <PageHeader title="Reports" description="A summary of the work done in a period, as PDF or CSV. Reports for a single analysis, document or test run are on that record's page." />

      <Panel title="Activity summary" aside={summary.data && (
        <span className="flex gap-3 text-sm">
          <a href={`/api/reports/summary/?${query}&type=pdf`} download className="font-medium text-electric hover:underline">Download PDF</a>
          <a href={`/api/reports/summary/?${query}&type=csv`} download className="font-medium text-electric hover:underline">Download CSV</a>
        </span>)}>
        <div className="mb-5 flex flex-wrap items-end gap-4">
          <label className="text-sm"><span className="mb-1 block font-medium">From</span>
            <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} className={`${inputClass} h-9 w-44`} /></label>
          <label className="text-sm"><span className="mb-1 block font-medium">To</span>
            <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} className={`${inputClass} h-9 w-44`} /></label>
          {summary.data && <p className="pb-2 text-sm text-muted">
            Covers {summary.data.scope === 'everyone' ? 'everyone\'s work' : 'your own work'} · rule set {summary.data.ruleset_version}</p>}
        </div>
        {summary.isPending ? <Loading /> : summary.isError ? <Notice tone="error">{summary.error.message}</Notice> : (
          <SummaryView data={summary.data} />
        )}
      </Panel>

      <Panel title="Reports for single records" className="mt-6">
        <ul className="space-y-2 text-sm">
          <li><Link to="/analyzer" className="font-medium text-electric hover:underline">Barcode analysis</Link> <span className="text-muted">PDF, CSV or JSON, from the File panel of each result.</span></li>
          {identity && <li><Link to="/documents?tab=records" className="font-medium text-electric hover:underline">Document analysis</Link> <span className="text-muted">PDF from the Record panel. It contains personal data and is marked confidential.</span></li>}
          <li><Link to="/test-lab" className="font-medium text-electric hover:underline">Test run</Link> <span className="text-muted">PDF, CSV, JSON or JUnit XML, from each run's results.</span></li>
        </ul>
      </Panel>
    </>
  )
}

function SummaryView({ data }: { data: Summary }) {
  const areas = [data.sections.analyzer, data.sections.documents, data.sections.ssn].filter(Boolean) as Section[]
  const lab = data.sections.test_lab
  return (
    <div className="space-y-6">
      <div className="-mx-5 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-y border-rule text-muted">
            <tr><th scope="col" className="px-5 py-2.5 font-medium">Area</th><th scope="col" className="px-5 py-2.5 font-medium">Total</th>
              <th scope="col" className="px-5 py-2.5 font-medium">Results</th><th scope="col" className="px-5 py-2.5 font-medium">Reviews</th></tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {areas.map((s) => (
              <tr key={s.label}>
                <th scope="row" className="px-5 py-3 font-medium">{s.label}</th>
                <td className="px-5 py-3 tabular-nums">{s.total}</td>
                <td className="px-5 py-3">{ORDER.filter((k) => s.by_status[k]).map((k) => `${STATUS[k as keyof typeof STATUS].label} ${s.by_status[k]}`).join(' · ') || '—'}</td>
                <td className="px-5 py-3">{s.reviews ? Object.entries(s.reviews).map(([k, v]) => `${REVIEW_WORDS[k] ?? k} ${v}`).join(' · ') || '—' : <span className="text-faint">n/a</span>}</td>
              </tr>
            ))}
            <tr>
              <th scope="row" className="px-5 py-3 font-medium">Testing Laboratory</th>
              <td className="px-5 py-3 tabular-nums">{lab.runs} run{lab.runs === 1 ? '' : 's'}</td>
              <td className="px-5 py-3" colSpan={2}>
                {lab.runs_with_failures} with failures or errors{lab.last_run && ` · latest ${lab.last_run.reference}: ${lab.last_run.passed} of ${lab.last_run.total} passed`}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium">Rules that most often failed or asked for review</h3>
        {data.rules.length === 0 ? <p className="text-sm text-muted">No failures or reviews in this period.</p> : (
          <ul className="divide-y divide-rule text-sm">
            {data.rules.map((r) => (
              <li key={r.code} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                <span className="min-w-0 flex-1">{r.name} <span className="font-mono text-xs text-faint">{r.code}</span></span>
                {r.failed > 0 && <span className="text-xs font-medium text-fail">{r.failed} failed</span>}
                {r.review > 0 && <span className="text-xs font-medium text-review">{r.review} needed review</span>}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-faint"><Link to="/rules" className="text-electric hover:underline">See what each rule checks</Link>. Counts only; this summary contains no personal data.</p>
      </div>
    </div>
  )
}
