import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, apiUpload } from '../../api/client'
import type { Fixture, Module, TestLabMeta, TestRun, TestRunDetail } from '../../api/testlab'
import type { Page } from '../../api/types'
import { Button, Loading, Notice, PageHeader, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { inputClass } from '../generator/shared'
import { describeExpectation, duration, moduleLabel } from './describe'
import { OutcomeBadge } from './shared'

const TABS = [{ key: 'runs', label: 'Runs' }, { key: 'fixtures', label: 'Fixtures' }] as const

function useMeta() {
  return useQuery({ queryKey: ['testlab', 'meta'], queryFn: () => api<TestLabMeta>('/api/test-lab/meta/') })
}

export function TestLabPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'fixtures' ? 'fixtures' : 'runs'
  return (
    <>
      <PageHeader title="Testing Laboratory"
        description="Run fixtures (inputs with results decided in advance) through the real analysis code, and see where actual results differ from expected ones or from the previous run." />
      <div role="tablist" aria-label="Testing Laboratory views" className="mb-6 flex gap-1 border-b border-rule">
        {TABS.map((t) => (
          <button key={t.key} role="tab" type="button" aria-selected={tab === t.key}
            onClick={() => setParams(t.key === 'runs' ? {} : { tab: t.key }, { replace: true })}
            className={cx('-mb-px border-b-2 px-4 py-2.5 text-sm',
              tab === t.key ? 'border-electric font-medium text-ink' : 'border-transparent text-muted hover:text-ink')}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'runs' ? <RunsTab /> : <FixturesTab />}
    </>
  )
}

/* ---------------- Runs ---------------- */

function scopeText(run: TestRun) {
  const parts = [run.scope.module ? moduleLabel(run.scope.module) : 'All modules']
  if (run.scope.tag) parts.push(`tag "${run.scope.tag}"`)
  if (run.scope.fixture_ids) parts.push(`${run.scope.fixture_ids.length} chosen`)
  return parts.join(', ')
}

function RunsTab() {
  const meta = useMeta()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [module, setModule] = useState('')
  const [tag, setTag] = useState('')
  const [note, setNote] = useState('')
  const runs = useQuery({
    queryKey: ['testlab', 'runs'],
    queryFn: () => api<Page<TestRun>>('/api/test-lab/runs/'),
    refetchInterval: (q) => (q.state.data?.results.some((r) => r.status === 'RUNNING') ? 1500 : false),
  })
  const start = useMutation({
    mutationFn: () => api<TestRunDetail>('/api/test-lab/runs/', { method: 'POST', body: { module, tag, note } }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['testlab'] })
      navigate(`/test-lab/runs/${run.id}`)
    },
  })
  const loadBuiltin = useLoadBuiltin()
  const m = meta.data
  const running = runs.data?.results.some((r) => r.status === 'RUNNING')

  return (
    <div className="space-y-6">
      <Panel title="Start a run" aside={m && `${m.fixtures_active} active fixture${m.fixtures_active === 1 ? '' : 's'}`}>
        {meta.isPending ? <Loading /> : !m ? null : m.fixtures_active === 0 ? (
          <div className="space-y-3 text-sm">
            <p className="text-muted">There are no fixtures yet. The standard set has {m.builtin_count} synthetic inputs covering both modules.</p>
            {m.can_edit_fixtures ? (
              <>
                {loadBuiltin.isError && <Notice tone="error">{loadBuiltin.error.message}</Notice>}
                <Button variant="primary" disabled={loadBuiltin.isPending} onClick={() => loadBuiltin.mutate()}>
                  {loadBuiltin.isPending ? 'Loading…' : 'Load the standard fixtures'}
                </Button>
              </>
            ) : <p className="text-muted">Ask an administrator or developer to load them.</p>}
          </div>
        ) : (
          <form className="flex flex-wrap items-end gap-4" onSubmit={(e: FormEvent) => { e.preventDefault(); start.mutate() }}>
            <label className="text-sm">
              <span className="mb-1 block font-medium">Module</span>
              <select value={module} onChange={(e) => setModule(e.target.value)} className={`${inputClass} h-9 w-48`}>
                <option value="">All modules</option>
                {m.modules.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block font-medium">Tag</span>
              <select value={tag} onChange={(e) => setTag(e.target.value)} className={`${inputClass} h-9 w-40`}>
                <option value="">Any tag</option>
                {m.tags.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="min-w-48 flex-1 text-sm">
              <span className="mb-1 block font-medium">Note (optional)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="e.g. after updating zxing-cpp"
                className={`${inputClass} h-9`} />
            </label>
            <Button type="submit" variant="primary" className="h-9" disabled={!m.can_run || start.isPending || running}>
              {start.isPending ? 'Starting…' : running ? 'A run is in progress' : 'Run tests'}
            </Button>
            {!m.can_run && <p className="w-full text-xs text-faint">Your role can view results but not start runs.</p>}
            {start.isError && <div className="w-full"><Notice tone="error">{start.error.message}</Notice></div>}
          </form>
        )}
        {m && (
          <p className="mt-4 border-t border-rule pt-3 text-xs text-faint">
            This build: DocumentLab {m.versions.app} · {m.versions.decoder} · {m.versions.ocr}
          </p>
        )}
      </Panel>

      <Panel title="Run history" aside={runs.data && `${runs.data.count} run${runs.data.count === 1 ? '' : 's'}`}>
        {runs.isPending ? <Loading /> : runs.isError ? <Notice tone="error">{runs.error.message}</Notice> : runs.data.results.length === 0 ? (
          <p className="text-sm text-muted">No runs yet.</p>
        ) : (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-rule text-muted">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">Run</th>
                  <th scope="col" className="px-5 py-3 font-medium">Scope</th>
                  <th scope="col" className="px-5 py-3 font-medium">Started</th>
                  <th scope="col" className="px-5 py-3 font-medium">Result</th>
                  <th scope="col" className="px-5 py-3 font-medium">Since previous run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {runs.data.results.map((r) => (
                  <tr key={r.id} className="hover:bg-canvas">
                    <td className="px-5 py-3 whitespace-nowrap">
                      <Link to={`/test-lab/runs/${r.id}`} className="font-mono text-xs text-electric hover:underline">{r.reference}</Link>
                      {r.note && <span className="block max-w-56 truncate text-xs text-muted">{r.note}</span>}
                    </td>
                    <td className="px-5 py-3 text-muted">{scopeText(r)}</td>
                    <td className="px-5 py-3 whitespace-nowrap text-muted">{formatDateTime(r.created_at)}{r.created_by ? ` · ${r.created_by}` : ''}</td>
                    <td className="px-5 py-3 whitespace-nowrap"><RunResult run={r} /></td>
                    <td className="px-5 py-3 whitespace-nowrap text-xs">
                      {r.status !== 'COMPLETE' ? <span className="text-faint">—</span> : !r.baseline ? <span className="text-faint">First run</span> : (
                        <>
                          {r.new_failures > 0 && <span className="mr-3 font-medium text-fail">{r.new_failures} new failure{r.new_failures === 1 ? '' : 's'}</span>}
                          {r.fixed > 0 && <span className="font-medium text-pass">{r.fixed} fixed</span>}
                          {r.new_failures === 0 && r.fixed === 0 && <span className="text-muted">No changes</span>}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}

export function RunResult({ run }: { run: TestRun }) {
  if (run.status === 'RUNNING') return <span className="text-sm text-muted">Running… {run.done} of {run.total}</span>
  if (run.status === 'INTERRUPTED') return <span className="text-sm text-review">Interrupted after {run.done} of {run.total}</span>
  return (
    <span className="flex items-center gap-2 text-sm">
      <OutcomeBadge outcome={run.failed || run.errors ? 'FAIL' : 'PASS'} />
      <span className="text-muted">{run.passed} of {run.total} passed{run.errors ? `, ${run.errors} error${run.errors === 1 ? '' : 's'}` : ''} · {duration(run.duration_ms)}</span>
    </span>
  )
}

function useLoadBuiltin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api<{ created: number; updated: number }>('/api/test-lab/fixtures/load-builtin/', { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['testlab'] }),
  })
}

/* ---------------- Fixtures ---------------- */

function FixturesTab() {
  const meta = useMeta()
  const [module, setModule] = useState('')
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const loadBuiltin = useLoadBuiltin()
  const list = useQuery({
    queryKey: ['testlab', 'fixtures', module],
    queryFn: () => api<Page<Fixture>>(`/api/test-lab/fixtures/?page_size=200${module ? `&module=${module}` : ''}`),
  })
  const canEdit = !!meta.data?.can_edit_fixtures

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Module</span>
          <select value={module} onChange={(e) => setModule(e.target.value)} className={`${inputClass} h-9 w-48`}>
            <option value="">All modules</option>
            <option value="analyzer">Barcode Analyzer</option>
            <option value="documents">Document Analysis</option>
          </select>
        </label>
        {canEdit && (
          <div className="flex gap-2">
            <Button disabled={loadBuiltin.isPending} onClick={() => loadBuiltin.mutate()}>
              {loadBuiltin.isPending ? 'Loading…' : meta.data?.builtin_loaded ? 'Refresh standard fixtures' : 'Load standard fixtures'}
            </Button>
            <Button variant="primary" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>{adding ? 'Close' : 'Add a fixture'}</Button>
          </div>
        )}
      </div>
      {loadBuiltin.isSuccess && <Notice tone="success">Standard fixtures: {loadBuiltin.data.created} added, {loadBuiltin.data.updated} refreshed.</Notice>}
      {loadBuiltin.isError && <Notice tone="error">{loadBuiltin.error.message}</Notice>}
      {adding && meta.data && <AddFixture meta={meta.data} onDone={() => setAdding(false)} />}

      <Panel title="Fixture library" aside={list.data && `${list.data.count} fixture${list.data.count === 1 ? '' : 's'}`}>
        {list.isPending ? <Loading /> : list.isError ? <Notice tone="error">{list.error.message}</Notice> : list.data.results.length === 0 ? (
          <p className="text-sm text-muted">No fixtures yet.</p>
        ) : (
          <ul className="-mx-5 -my-5 divide-y divide-rule">
            {list.data.results.map((f) => (
              <FixtureRow key={f.id} fixture={f} canEdit={canEdit} open={open === f.id} onToggle={() => setOpen(open === f.id ? null : f.id)} />
            ))}
          </ul>
        )}
      </Panel>
      <p className="text-xs text-faint">
        Fixtures hold synthetic data only. DocumentLab refuses identity barcodes, and any document that doesn't use ICAO's fictional specimen state (UTO).
      </p>
    </div>
  )
}

function FixtureRow({ fixture: f, canEdit, open, onToggle }: { fixture: Fixture; canEdit: boolean; open: boolean; onToggle: () => void }) {
  const queryClient = useQueryClient()
  const toggle = useMutation({
    mutationFn: () => api<Fixture>(`/api/test-lab/fixtures/${f.id}/`, { method: 'PATCH', body: { active: !f.active } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['testlab'] }),
  })
  const remove = useMutation({
    mutationFn: () => api<void>(`/api/test-lab/fixtures/${f.id}/`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['testlab'] }),
  })
  const rules = describeExpectation(f.expected)
  return (
    <li className={cx(!f.active && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
        <button type="button" onClick={onToggle} aria-expanded={open} className="min-w-0 flex-1 text-left">
          <span className="text-sm font-medium hover:text-electric">{f.name}</span>
          {f.is_builtin && <span className="ml-2 rounded border border-rule px-1.5 py-px text-[0.7rem] text-muted">Standard</span>}
          {!f.active && <span className="ml-2 text-xs text-faint">Switched off</span>}
          <span className="block truncate text-xs text-muted">
            {moduleLabel(f.module)} · {f.input_type === 'mrz_text' ? 'Typed MRZ' : f.file_kind.toUpperCase()}
            {f.tags.length > 0 && ` · ${f.tags.join(', ')}`}
          </span>
        </button>
        <span className="text-xs text-muted">{f.last_result ? <OutcomeBadge outcome={f.last_result.outcome} /> : 'Not run yet'}</span>
      </div>
      {open && (
        <div className="grid gap-5 border-t border-rule bg-canvas px-5 py-4 text-sm md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            {f.description && <p className="mb-3">{f.description}</p>}
            {f.links.file && ['png', 'jpeg'].includes(f.file_kind) && (
              <img src={f.links.file} alt={`Input for ${f.name}`} className="max-h-56 rounded border border-rule bg-white" />
            )}
            {f.links.file && f.file_kind === 'pdf' && <a href={f.links.file} target="_blank" rel="noreferrer" className="text-electric hover:underline">Open the PDF</a>}
            {f.mrz_text && <pre className="overflow-x-auto rounded bg-ink p-3 font-mono text-xs leading-relaxed text-white">{f.mrz_text}</pre>}
            {f.options.expected_value && <p className="mt-2 text-xs text-muted">Analysed with expected value <span className="font-mono">{f.options.expected_value}</span></p>}
          </div>
          <div>
            <h3 className="mb-1.5 text-xs font-medium text-muted">Expected</h3>
            <ul className="list-disc space-y-1 pl-4">{rules.map((r) => <li key={r}>{r}</li>)}</ul>
            {f.last_result && (
              <p className="mt-3 text-xs text-muted">Last run: <Link to={`/test-lab/runs/${f.last_result.run_id}`} className="text-electric hover:underline">{f.last_result.run_reference}</Link></p>
            )}
            {canEdit && (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button disabled={toggle.isPending} onClick={() => toggle.mutate()}>{f.active ? 'Switch off' : 'Switch on'}</Button>
                {!f.is_builtin && <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>Delete</Button>}
              </div>
            )}
            {(toggle.isError || remove.isError) && <div className="mt-2"><Notice tone="error">{(toggle.error ?? remove.error)!.message}</Notice></div>}
          </div>
        </div>
      )}
    </li>
  )
}

const STATUS_CHOICES = [['PASS', 'Pass'], ['FAIL', 'Fail'], ['REVIEW_REQUIRED', 'Needs review'], ['NOT_SUPPORTED', 'Not supported']] as const

function AddFixture({ meta, onDone }: { meta: TestLabMeta; onDone: () => void }) {
  const queryClient = useQueryClient()
  const [module, setModule] = useState<Module>('analyzer')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [input, setInput] = useState<'file' | 'mrz'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [mrz, setMrz] = useState('')
  const [statuses, setStatuses] = useState<string[]>(['PASS'])
  const [extra, setExtra] = useState('')
  const [option, setOption] = useState('')
  const [synthetic, setSynthetic] = useState(false)
  const imagesAllowed = module === 'analyzer' || meta.can_add_document_images
  const useMrz = module === 'documents' && (input === 'mrz' || !imagesAllowed)

  const save = useMutation({
    mutationFn: () => {
      let expected: Record<string, unknown> = {}
      if (extra.trim()) {
        try { expected = JSON.parse(extra) } catch { throw new Error('More expectations: that isn\'t valid JSON.') }
      }
      if (statuses.length) expected = { status: statuses, ...expected }
      const form = new FormData()
      form.append('name', name)
      form.append('description', description)
      form.append('module', module)
      form.append('tags', tags)
      form.append('expected', JSON.stringify(expected))
      form.append('synthetic', String(synthetic))
      if (option.trim()) form.append('options', JSON.stringify(module === 'analyzer' ? { expected_value: option.trim() } : { document_type: option }))
      if (useMrz) form.append('mrz_text', mrz)
      else if (file) form.append('file', file)
      return apiUpload<Fixture>('/api/test-lab/fixtures/', form)
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['testlab'] }); onDone() },
  })

  const ready = name.trim() && synthetic && (useMrz ? mrz.trim() : file) && (statuses.length || extra.trim())

  return (
    <Panel title="Add a fixture">
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (ready) save.mutate() }}>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm"><span className="mb-1 block font-medium">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className={`${inputClass} h-9`} /></label>
          <label className="text-sm"><span className="mb-1 block font-medium">Tags (comma-separated)</span>
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="shelf, degraded" className={`${inputClass} h-9`} /></label>
        </div>
        <label className="block text-sm"><span className="mb-1 block font-medium">What this tests (optional)</span>
          <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} className={`${inputClass} h-9`} /></label>

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Module</legend>
          <div className="flex gap-5 text-sm">
            {(['analyzer', 'documents'] as const).map((m) => (
              <label key={m} className="flex items-center gap-2">
                <input type="radio" name="fixture-module" checked={module === m} onChange={() => { setModule(m); setOption('') }} className="accent-electric" />
                {moduleLabel(m)}
              </label>
            ))}
          </div>
        </fieldset>

        {module === 'documents' && imagesAllowed && (
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">Input</legend>
            <div className="flex gap-5 text-sm">
              <label className="flex items-center gap-2"><input type="radio" name="fixture-input" checked={input === 'mrz'} onChange={() => setInput('mrz')} className="accent-electric" /> Typed MRZ</label>
              <label className="flex items-center gap-2"><input type="radio" name="fixture-input" checked={input === 'file'} onChange={() => setInput('file')} className="accent-electric" /> Image or PDF</label>
            </div>
          </fieldset>
        )}
        {useMrz ? (
          <div className="text-sm">
            <label htmlFor="fixture-mrz" className="mb-1 block font-medium">Machine-readable zone</label>
            <textarea id="fixture-mrz" value={mrz} onChange={(e) => setMrz(e.target.value.toUpperCase())} rows={3} spellCheck={false}
              aria-describedby="fixture-mrz-hint" className={`${inputClass} py-2 font-mono text-[0.85rem]`} />
            <p id="fixture-mrz-hint" className="mt-1 text-xs text-faint">
              Must use the specimen state UTO.{!imagesAllowed && ' Only administrators can add document images.'}
            </p>
          </div>
        ) : (
          <label className="block text-sm"><span className="mb-1 block font-medium">Image or PDF</span>
            <input type="file" accept=".png,.jpg,.jpeg,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:h-9 file:rounded-md file:border file:border-rule file:bg-paper file:px-3.5 file:text-sm file:font-medium" />
          </label>
        )}
        {module === 'analyzer' ? (
          <div className="text-sm">
            <label htmlFor="fixture-expected-value" className="mb-1 block font-medium">Analyse with expected value (optional)</label>
            <input id="fixture-expected-value" value={option} onChange={(e) => setOption(e.target.value)} aria-describedby="fixture-expected-value-hint"
              className={`${inputClass} h-9 sm:max-w-sm`} />
            <p id="fixture-expected-value-hint" className="mt-1 text-xs text-faint">Passed to the Barcode Analyzer, as on its own page.</p>
          </div>
        ) : (
          <label className="block text-sm"><span className="mb-1 block font-medium">Document type</span>
            <select value={option} onChange={(e) => setOption(e.target.value)} className={`${inputClass} h-9 sm:max-w-xs`}>
              <option value="">Detect automatically</option>
              <option value="passport">Passport</option>
              <option value="id_card">ID card</option>
            </select>
          </label>
        )}

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Expected overall result (any of)</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
            {STATUS_CHOICES.map(([key, label]) => (
              <label key={key} className="flex items-center gap-2">
                <input type="checkbox" checked={statuses.includes(key)} className="accent-electric"
                  onChange={(e) => setStatuses((s) => e.target.checked ? [...s, key] : s.filter((x) => x !== key))} />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">More expectations (JSON, optional)</summary>
          <textarea value={extra} onChange={(e) => setExtra(e.target.value)} rows={4} spellCheck={false}
            placeholder={module === 'analyzer' ? '{"barcode_count": 1, "barcodes": [{"format": "EAN-13", "text": "5901234123457"}]}'
              : '{"detected_type": "passport", "fields": {"surname": "ERIKSSON"}, "checks": {"mrz.check_digit.composite": "PASS"}}'}
            className={`${inputClass} mt-2 py-2 font-mono text-xs`} />
          <span className="mt-1 block text-xs text-faint">
            {module === 'analyzer' ? 'Keys: barcode_count, barcodes, checks, max_duration_ms.' : 'Keys: detected_type, fields, checks, max_duration_ms.'}
          </span>
        </details>

        <label className="flex items-start gap-2.5 rounded-md border border-rule bg-canvas px-3.5 py-3 text-sm">
          <input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} className="mt-0.5 size-4 shrink-0 accent-electric" />
          <span>This fixture contains only synthetic (invented) data, not a real person's document or information.</span>
        </label>
        {save.isError && <Notice tone="error">{save.error.message}</Notice>}
        <Button type="submit" variant="primary" disabled={!ready || save.isPending}>{save.isPending ? 'Checking and saving…' : 'Save fixture'}</Button>
      </form>
    </Panel>
  )
}
