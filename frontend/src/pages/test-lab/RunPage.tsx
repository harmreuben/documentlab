import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { api } from '../../api/client'
import type { CaseResult, Fixture, TestLabMeta, TestRunDetail } from '../../api/testlab'
import { StatusBadge } from '../../components/StatusBadge'
import { Loading, Notice, Panel, Button } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { duration, moduleLabel } from './describe'
import { ChangeLabel, OutcomeBadge } from './shared'
import { RunResult } from './TestLabPage'

const FILTERS = [['all', 'All'], ['problems', 'Failed or errors'], ['changed', 'Changed since previous run']] as const
type Filter = (typeof FILTERS)[number][0]

export function RunPage() {
  const { id } = useParams()
  const [filter, setFilter] = useState<Filter>('all')
  const [open, setOpen] = useState<number | null>(null)
  const run = useQuery({
    queryKey: ['testlab', 'run', id],
    queryFn: () => api<TestRunDetail>(`/api/test-lab/runs/${id}/`),
    refetchInterval: (q) => (q.state.data?.status === 'RUNNING' ? 1500 : false),
  })
  const meta = useQuery({ queryKey: ['testlab', 'meta'], queryFn: () => api<TestLabMeta>('/api/test-lab/meta/') })

  if (run.isPending) return <Loading label="Loading the run" />
  if (run.isError) return <Notice tone="error">{run.error.message}</Notice>
  const r = run.data
  const cases = r.cases.filter((c) => filter === 'all' ? true : filter === 'problems' ? c.outcome !== 'PASS'
    : c.change === 'new_failure' || c.change === 'fixed')

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-4 text-sm">
        <Link to="/test-lab" className="text-muted hover:text-electric">Testing Laboratory</Link>
        <span className="mx-2 text-faint">/</span><span className="font-mono text-xs">{r.reference}</span>
      </nav>

      <header className="mb-6 rounded-[10px] border border-rule bg-paper px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[1.5rem] leading-tight font-semibold">
              {r.status === 'RUNNING' ? 'Running…' : r.status === 'INTERRUPTED' ? 'This run was interrupted'
                : r.failed || r.errors ? `${r.failed + r.errors} of ${r.total} tests didn't behave as expected` : `All ${r.total} tests behaved as expected`}
            </h1>
            <p className="mt-1 text-sm text-muted">
              {formatDateTime(r.created_at)}{r.created_by ? ` by ${r.created_by}` : ''}{r.note ? ` · ${r.note}` : ''}
            </p>
          </div>
          <RunResult run={r} />
        </div>
        {r.status === 'RUNNING' && (
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-canvas" role="progressbar" aria-valuemin={0} aria-valuemax={r.total} aria-valuenow={r.done}
            aria-label="Run progress">
            <div className="h-full bg-electric transition-all" style={{ width: `${(100 * r.done) / Math.max(1, r.total)}%` }} />
          </div>
        )}
        {r.status === 'INTERRUPTED' && (
          <p className="mt-3 text-sm text-review">It stopped before every fixture had a result, usually because the server was restarted. Start a new run.</p>
        )}
        <dl className="mt-4 grid gap-x-8 gap-y-2 border-t border-rule pt-3 text-xs sm:grid-cols-3">
          <div><dt className="text-muted">Build</dt><dd>DocumentLab {r.versions.app ?? '?'}{r.versions.rules ? ` · rules ${r.versions.rules}` : ''} · {r.versions.decoder ?? '?'}</dd></div>
          <div><dt className="text-muted">OCR</dt><dd>{r.versions.ocr ?? '?'}</dd></div>
          <div><dt className="text-muted">Compared with</dt><dd>{r.baseline
            ? <Link to={`/test-lab/runs/${r.baseline.id}`} className="font-mono text-electric hover:underline">{r.baseline.reference}</Link>
            : 'Nothing (first run)'}</dd></div>
        </dl>
      </header>

      {r.status === 'COMPLETE' && r.baseline && (r.new_failures > 0 || r.fixed > 0) && (
        <div className="mb-6">
          <Notice tone={r.new_failures ? 'error' : 'success'}>
            Since {r.baseline.reference}: {r.new_failures > 0 && `${r.new_failures} test${r.new_failures === 1 ? '' : 's'} that used to pass now fail${r.new_failures === 1 ? 's' : ''}. `}
            {r.fixed > 0 && `${r.fixed} test${r.fixed === 1 ? '' : 's'} that used to fail now pass${r.fixed === 1 ? 'es' : ''}.`}
          </Notice>
        </div>
      )}

      <Panel title="Results" aside={
        <span className="flex gap-3 text-xs">
          <a href={r.links.pdf} className="text-electric hover:underline">PDF</a>
          <a href={r.links.csv} className="text-electric hover:underline">CSV</a>
          <a href={r.links.json} className="text-electric hover:underline">JSON</a>
          <a href={r.links.junit} className="text-electric hover:underline">JUnit XML</a>
        </span>}>
        <div role="radiogroup" aria-label="Show" className="mb-4 flex flex-wrap gap-2">
          {FILTERS.map(([key, label]) => (
            <button key={key} type="button" role="radio" aria-checked={filter === key} onClick={() => setFilter(key)}
              className={cx('rounded-full border px-3 py-1 text-xs', filter === key ? 'border-ink bg-ink text-white' : 'border-rule text-muted hover:text-ink')}>
              {label}
            </button>
          ))}
        </div>
        {cases.length === 0 ? <p className="text-sm text-muted">{r.cases.length ? 'Nothing matches this filter.' : 'No results yet.'}</p> : (
          <ul className="-mx-5 -mb-5 divide-y divide-rule border-t border-rule">
            {cases.map((c) => (
              <CaseRow key={c.id} c={c} open={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)}
                canAdopt={!!meta.data?.can_edit_fixtures} />
            ))}
          </ul>
        )}
      </Panel>
    </>
  )
}

function CaseRow({ c, open, onToggle, canAdopt }: { c: CaseResult; open: boolean; onToggle: () => void; canAdopt: boolean }) {
  const queryClient = useQueryClient()
  const adopt = useMutation({
    mutationFn: () => api<Fixture>(`/api/test-lab/fixtures/${c.fixture}/adopt/`, { method: 'POST', body: { case_id: c.id } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['testlab', 'fixtures'] }),
  })
  const differences = c.comparisons.filter((x) => !x.passed)
  return (
    <li>
      <button type="button" onClick={onToggle} aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-left hover:bg-canvas">
        <OutcomeBadge outcome={c.outcome} />
        <span className="min-w-0 flex-1">
          <span className="text-sm font-medium">{c.fixture_name}</span>
          <span className="block truncate text-xs text-muted">
            {moduleLabel(c.module)}
            {differences.length > 0 && ` · ${differences[0].label}: expected ${differences[0].expected}, got ${differences[0].actual}`}
            {c.error && ` · ${c.error}`}
          </span>
        </span>
        <ChangeLabel change={c.change} />
        <span className="w-16 text-right text-xs text-faint tabular-nums">{duration(c.duration_ms)}</span>
      </button>
      {open && (
        <div className="border-t border-rule bg-canvas px-5 py-4">
          {c.error && <Notice tone="error">{c.error}</Notice>}
          {c.comparisons.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr><th scope="col" className="py-1.5 pr-4 font-medium">Expectation</th><th scope="col" className="py-1.5 pr-4 font-medium">Expected</th>
                    <th scope="col" className="py-1.5 pr-4 font-medium">Actual</th><th scope="col" className="py-1.5 font-medium"><span className="sr-only">Matches</span></th></tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {c.comparisons.map((row) => (
                    <tr key={row.label} className={cx(!row.passed && 'text-fail')}>
                      <th scope="row" className="py-2 pr-4 font-medium">{row.label}</th>
                      <td className="py-2 pr-4 break-all">{row.expected}</td>
                      <td className="py-2 pr-4 break-all">{row.actual}</td>
                      <td className="py-2 font-medium">{row.passed ? <span className="text-pass">Matches</span> : 'Differs'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {c.actual && (
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted">The module said:</span> <StatusBadge status={c.actual.status} /> <span>{c.actual.summary}</span>
            </p>
          )}
          {c.previous_outcome && <p className="mt-2 text-xs text-muted">Previous run: {c.previous_outcome === 'PASS' ? 'passed' : c.previous_outcome === 'FAIL' ? 'failed' : 'error'}.</p>}
          {canAdopt && c.outcome === 'FAIL' && c.actual && c.fixture && (
            <div className="mt-4 border-t border-rule pt-3">
              {adopt.isSuccess ? <Notice tone="success">Saved as this fixture's expected result. The next run will use it.</Notice> : (
                <>
                  <Button disabled={adopt.isPending} onClick={() => adopt.mutate()}>Use this result as the expected result</Button>
                  <p className="mt-1.5 text-xs text-faint">Only if you've checked that the new behaviour is correct. Standard fixtures can't be changed this way.</p>
                  {adopt.isError && <div className="mt-2"><Notice tone="error">{adopt.error.message}</Notice></div>}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  )
}
