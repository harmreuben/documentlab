import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { CoverageLevel, Rule, RulesResponse } from '../../api/rules'
import { STATUS, StatusBadge } from '../../components/StatusBadge'
import { Loading, Notice, PageHeader, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { inputClass } from '../generator/shared'

const COVERAGE_STYLE: Record<CoverageLevel, string> = {
  full: 'text-pass', partial: 'text-review', none: 'text-fail', outside: 'text-muted',
}
const SEVERITY_STYLE: Record<Rule['severity'], string> = {
  blocking: 'border-[#F1C4C7] text-fail', review: 'border-[#F3D5A8] text-review', information: 'border-rule text-muted',
}
const SEVERITY_WORD: Record<Rule['severity'], string> = { blocking: 'Can fail', review: 'Review only', information: 'Information' }

export function RulesPage() {
  const rules = useQuery({ queryKey: ['rules'], queryFn: () => api<RulesResponse>('/api/rules/') })
  const [module, setModule] = useState('')
  const [coverage, setCoverage] = useState('')
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState<string | null>(null)

  const shown = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (rules.data?.rules ?? []).filter((r) => (!module || r.module === module) && (!coverage || r.coverage.level === coverage)
      && (!term || `${r.name} ${r.code} ${r.checks}`.toLowerCase().includes(term)))
  }, [rules.data, module, coverage, search])

  if (rules.isPending) return <Loading label="Loading the rules" />
  if (rules.isError) return <Notice tone="error">{rules.error.message}</Notice>
  const d = rules.data
  const groups = d.modules.map((m) => ({ ...m, rules: shown.filter((r) => r.module === m.key) })).filter((g) => g.rules.length)

  return (
    <>
      <PageHeader title="Validation Rules"
        description={`Every check DocumentLab makes: what it looks at, what it can decide, where the rule comes from and how well the Testing Laboratory covers it. Rule set ${d.ruleset_version}.`} />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {d.coverage_levels.map((level) => (
          <button key={level.key} type="button" onClick={() => setCoverage(coverage === level.key ? '' : level.key)} aria-pressed={coverage === level.key}
            className={cx('rounded-[10px] border bg-paper px-5 py-4 text-left hover:border-electric',
              coverage === level.key ? 'border-electric ring-1 ring-electric' : 'border-rule')}>
            <span className="text-sm text-muted">{level.label}</span>
            <span className={cx('mt-1 block text-[1.75rem] leading-none font-semibold tabular-nums', COVERAGE_STYLE[level.key])}>
              {d.coverage_summary[level.key]}
            </span>
          </button>
        ))}
      </div>
      <p className="mb-6 text-sm text-muted">
        {d.measured_from.latest_run ? (
          <>Coverage is measured from the latest result of {d.measured_from.fixtures} active fixtures, up to run{' '}
            <Link to={`/test-lab/runs/${d.measured_from.latest_run.id}`} className="font-mono text-xs text-electric hover:underline">{d.measured_from.latest_run.reference}</Link>{' '}
            ({formatDateTime(d.measured_from.latest_run.at)}). "Fully tested" means fixtures have seen every result that matters: pass and fail (or ask for review), or the rule's only possible result.</>
        ) : <>No test runs yet, so no coverage can be measured. <Link to="/test-lab" className="text-electric hover:underline">Run the Testing Laboratory</Link> first.</>}
      </p>

      <div className="mb-4 flex flex-wrap items-end gap-4">
        <label className="text-sm"><span className="mb-1 block text-muted">Area</span>
          <select value={module} onChange={(e) => setModule(e.target.value)} className={`${inputClass} h-9 w-52`}>
            <option value="">All areas</option>
            {d.modules.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </label>
        <label className="min-w-56 flex-1 text-sm sm:max-w-sm"><span className="mb-1 block text-muted">Search</span>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. check digit" className={`${inputClass} h-9`} />
        </label>
        <span className="pb-2 text-sm text-muted">{shown.length} of {d.rules.length} rules</span>
      </div>

      {groups.length === 0 ? <Panel><p className="text-sm text-muted">No rules match.</p></Panel> : (
        <div className="space-y-6">
          {groups.map((g) => (
            <Panel key={g.key} title={g.label} aside={`${g.rules.length} rule${g.rules.length === 1 ? '' : 's'}`}>
              <ul className="-mx-5 -my-5 divide-y divide-rule">
                {g.rules.map((r) => <RuleRow key={r.code} rule={r} open={open === r.code} onToggle={() => setOpen(open === r.code ? null : r.code)} />)}
              </ul>
            </Panel>
          ))}
        </div>
      )}
    </>
  )
}

function RuleRow({ rule: r, open, onToggle }: { rule: Rule; open: boolean; onToggle: () => void }) {
  return (
    <li>
      <button type="button" onClick={onToggle} aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-left hover:bg-canvas">
        <span className="min-w-0 flex-1">
          <span className="text-sm font-medium">{r.name}</span>
          <span className="ml-2 font-mono text-[0.72rem] text-faint">{r.code}</span>
        </span>
        <span className={cx('rounded-full border px-2 py-0.5 text-[0.7rem] font-medium', SEVERITY_STYLE[r.severity])}>{SEVERITY_WORD[r.severity]}</span>
        <span className="w-10 text-xs text-muted tabular-nums">v{r.version}</span>
        <span className={cx('w-44 text-right text-xs font-medium', COVERAGE_STYLE[r.coverage.level])}>{r.coverage.label}</span>
      </button>
      {open && (
        <div className="grid gap-6 border-t border-rule bg-canvas px-5 py-4 text-sm lg:grid-cols-2">
          <div className="space-y-4">
            <p>{r.checks}</p>
            <div>
              <h3 className="mb-1.5 text-xs font-medium text-muted">Possible results</h3>
              <ul className="space-y-1.5">
                {Object.entries(r.outcomes).map(([status, when]) => (
                  <li key={status} className="flex items-start gap-3"><span className="w-28 shrink-0"><StatusBadge status={status as keyof typeof STATUS} /></span><span>{when}</span></li>
                ))}
              </ul>
            </div>
            {Object.keys(r.parameters).length > 0 && (
              <div>
                <h3 className="mb-1.5 text-xs font-medium text-muted">Limits in use</h3>
                <dl className="space-y-1">
                  {Object.entries(r.parameters).map(([k, v]) => (
                    <div key={k} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3"><dt className="text-muted">{k}</dt><dd className="font-medium tabular-nums">{v}</dd></div>
                  ))}
                </dl>
              </div>
            )}
          </div>
          <div className="space-y-4">
            <dl className="space-y-1">
              <div className="grid grid-cols-[6rem_1fr] gap-3"><dt className="text-muted">Source</dt><dd>{r.reference}</dd></div>
              <div className="grid grid-cols-[6rem_1fr] gap-3"><dt className="text-muted">Version</dt><dd>{r.version}, since DocumentLab {r.since}</dd></div>
            </dl>
            {r.changes.length > 0 && (
              <div>
                <h3 className="mb-1.5 text-xs font-medium text-muted">Changes</h3>
                <ul className="space-y-1.5">{r.changes.map((c) => <li key={c.version}><span className="font-medium">v{c.version}</span> <span className="text-muted">({c.app_version})</span> {c.note}</li>)}</ul>
              </div>
            )}
            <div>
              <h3 className="mb-1.5 text-xs font-medium text-muted">Test coverage</h3>
              {r.coverage.level === 'outside' ? (
                <p className="text-muted">Not part of the Testing Laboratory. It's covered by the automated test suite, which also fails if this rule stops matching the code.</p>
              ) : r.coverage.exercised_by.length === 0 ? (
                <p className="text-fail">No fixture has produced this check yet.</p>
              ) : (
                <>
                  <p className="mb-1.5">Seen as {r.coverage.statuses.map((s) => STATUS[s]?.label ?? s).join(', ')} across {r.coverage.exercised_by.length} fixture{r.coverage.exercised_by.length === 1 ? '' : 's'}.
                    {r.coverage.asserted_by.length > 0 && ` ${r.coverage.asserted_by.length} check${r.coverage.asserted_by.length === 1 ? 's' : ''} it explicitly.`}</p>
                  <ul className="max-h-40 space-y-0.5 overflow-auto text-xs">
                    {r.coverage.exercised_by.map((f) => (
                      <li key={f.id}>{f.name} <span className="text-muted">({f.statuses.map((s) => STATUS[s]?.label ?? s).join(', ')})</span>
                        {r.coverage.asserted_by.some((a) => a.id === f.id) && <span className="ml-1 font-medium text-pass">asserted</span>}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </li>
  )
}
