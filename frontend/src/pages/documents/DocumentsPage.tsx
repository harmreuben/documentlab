import { useState, type FormEvent } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, apiUpload } from '../../api/client'
import type { Comparison, DocumentAnalysis, DocumentListItem, DocumentsMeta, SsnResult } from '../../api/documents'
import type { Page } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Loading, Notice, PageHeader, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { inputClass } from '../generator/shared'

const TABS = [
  { key: 'analyse', label: 'Analyse' },
  { key: 'records', label: 'Records' },
  { key: 'compare', label: 'Compare' },
  { key: 'ssn', label: 'SSN format check' },
] as const
type Tab = (typeof TABS)[number]['key']

export function useDocumentsMeta() {
  return useQuery({ queryKey: ['documents', 'meta'], queryFn: () => api<DocumentsMeta>('/api/documents/meta/'), staleTime: 60_000 })
}

export function DocumentsPage() {
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.key === params.get('tab'))?.key ?? 'analyse') as Tab
  return (
    <>
      <PageHeader title="Document Analysis"
        description="Technical checks on passports, ID cards and driving licences: OCR, machine-readable zones, licence barcodes, dates and consistency. These checks can't show that a document is genuine." />
      <div role="tablist" aria-label="Document Analysis views" className="mb-6 flex gap-1 overflow-x-auto border-b border-rule">
        {TABS.map((t) => (
          <button key={t.key} role="tab" type="button" aria-selected={tab === t.key}
            onClick={() => setParams(t.key === 'analyse' ? {} : { tab: t.key }, { replace: true })}
            className={cx('-mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm',
              tab === t.key ? 'border-electric font-medium text-ink' : 'border-transparent text-muted hover:text-ink')}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'analyse' && <AnalyseTab />}
      {tab === 'records' && <RecordsTab />}
      {tab === 'compare' && <CompareTab />}
      {tab === 'ssn' && <SsnTab />}
    </>
  )
}

/* ---------------- Analyse ---------------- */

function AnalyseTab() {
  const meta = useDocumentsMeta()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'upload' | 'typed'>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [mrzText, setMrzText] = useState('')
  const [docType, setDocType] = useState('auto')
  const [authorised, setAuthorised] = useState(false)

  const run = useMutation({
    mutationFn: () => {
      if (mode === 'upload') {
        const form = new FormData()
        form.append('file', file!)
        form.append('document_type', docType)
        form.append('authorised', 'true')
        return apiUpload<DocumentAnalysis>('/api/documents/analyses/', form)
      }
      return api<DocumentAnalysis>('/api/documents/analyses/', {
        method: 'POST', body: { mrz_text: mrzText, document_type: docType, authorised: true },
      })
    },
    onSuccess: (record) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.setQueryData(['documents', 'analysis', String(record.id)], record)
      navigate(`/documents/${record.id}`)
    },
  })

  const ready = authorised && (mode === 'upload' ? !!file : mrzText.trim().length > 0)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (ready) run.mutate()
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <Panel title="Analyse a document">
        <form onSubmit={submit} className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Input</legend>
            <div className="inline-flex rounded-md border border-rule p-0.5">
              {([['upload', 'Upload an image'], ['typed', 'Type the MRZ']] as const).map(([key, label]) => (
                <label key={key} className={cx('cursor-pointer rounded px-3 py-1.5 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-electric',
                  mode === key ? 'bg-ink text-white' : 'text-muted hover:text-ink')}>
                  <input type="radio" name="mode" value={key} checked={mode === key} onChange={() => { setMode(key); run.reset() }} className="sr-only" />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <label htmlFor="doc-type" className="mb-1.5 block text-sm font-medium">Document type</label>
            <select id="doc-type" value={docType} onChange={(e) => setDocType(e.target.value)} className={`${inputClass} h-9 sm:max-w-xs`}>
              {(meta.data?.types ?? [{ key: 'auto', label: 'Detect automatically' }]).map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
          </div>

          {mode === 'upload' ? (
            <div>
              <label htmlFor="doc-file" className="mb-1.5 block text-sm font-medium">Image or PDF</label>
              <input id="doc-file" type="file" accept=".png,.jpg,.jpeg,.pdf" onChange={(e) => { setFile(e.target.files?.[0] ?? null); run.reset() }}
                className="block w-full text-sm file:mr-3 file:h-9 file:rounded-md file:border file:border-rule file:bg-paper file:px-3.5 file:text-sm file:font-medium hover:file:bg-canvas" />
              <p className="mt-1 text-xs text-faint">The photo page of a passport or ID card, or the barcode side of a licence. Flat, in focus, evenly lit.</p>
            </div>
          ) : (
            <div>
              <label htmlFor="mrz-text" className="mb-1.5 block text-sm font-medium">Machine-readable zone</label>
              <textarea id="mrz-text" value={mrzText} onChange={(e) => setMrzText(e.target.value.toUpperCase())} rows={3} spellCheck={false}
                autoComplete="off" placeholder={'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10'}
                className={`${inputClass} py-2 font-mono text-[0.85rem] leading-relaxed`} />
              <p className="mt-1 text-xs text-faint">2 lines of 44 or 36 characters, or 3 lines of 30. The example is ICAO's fictional specimen.</p>
            </div>
          )}

          <label className="flex items-start gap-2.5 rounded-md border border-rule bg-canvas px-3.5 py-3 text-sm">
            <input type="checkbox" checked={authorised} onChange={(e) => setAuthorised(e.target.checked)} className="mt-0.5 size-4 shrink-0 accent-electric" />
            <span>I'm authorised to process this document, and I'm handling it under our data-protection rules.</span>
          </label>

          {run.isError && <Notice tone="error">{run.error.message}</Notice>}
          <Button type="submit" variant="primary" className="h-10 px-5" disabled={!ready || run.isPending}>
            {run.isPending ? (mode === 'upload' ? 'Reading the document…' : 'Checking…') : 'Analyse document'}
          </Button>
        </form>
      </Panel>

      <Panel title="How identity data is handled">
        <ul className="space-y-3 text-sm">
          <li><span className="font-medium">Deleted automatically.</span> <span className="text-muted">
            Names, numbers, dates, text and images are deleted {meta.data ? `${meta.data.retention_days} days` : 'a set time'} after analysis, or sooner if you choose.</span></li>
          <li><span className="font-medium">Limited access.</span> <span className="text-muted">Only analysts, reviewers and administrators can open this section. Analysts see their own records.</span></li>
          <li><span className="font-medium">Kept out of logs.</span> <span className="text-muted">The audit log records that a document was checked, never what it contained.</span></li>
          <li><span className="font-medium">Read on this computer.</span> <span className="text-muted">
            {meta.data?.ocr.available ? `OCR runs locally (${meta.data.ocr.engine}).` : 'OCR is not available here, so images can\'t be read. Typed MRZs still work.'}</span></li>
        </ul>
        <p className="mt-4 border-t border-rule pt-4 text-xs text-faint">
          Passing every check means the data is internally consistent. It doesn't prove the document is genuine or belongs to the person presenting it.
        </p>
      </Panel>
    </div>
  )
}

/* ---------------- Records ---------------- */

function RecordsTab() {
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const params = new URLSearchParams({ page: String(page) })
  if (status) params.set('status', status)
  const list = useQuery({
    queryKey: ['documents', 'list', status, page],
    queryFn: () => api<Page<DocumentListItem>>(`/api/documents/analyses/?${params}`),
    placeholderData: keepPreviousData,
  })
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / 25)) : 1

  return (
    <>
      <div className="mb-4">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Result</span>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className={`${inputClass} h-9 w-44`}>
            <option value="">Any result</option>
            <option value="PASS">Pass</option>
            <option value="FAIL">Fail</option>
            <option value="REVIEW_REQUIRED">Needs review</option>
          </select>
        </label>
      </div>
      <Panel title="Document records" aside={list.data && `${list.data.count} found`}>
        {list.isPending ? <Loading /> : list.isError ? <Notice tone="error">{list.error.message}</Notice> : list.data.results.length === 0 ? (
          <p className="text-sm text-muted">No documents analysed yet.</p>
        ) : (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-rule text-muted">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">Reference</th>
                  <th scope="col" className="px-5 py-3 font-medium">Document</th>
                  <th scope="col" className="px-5 py-3 font-medium">Holder</th>
                  <th scope="col" className="px-5 py-3 font-medium">Number</th>
                  <th scope="col" className="px-5 py-3 font-medium">Analysed</th>
                  <th scope="col" className="px-5 py-3 font-medium">Data deleted</th>
                  <th scope="col" className="px-5 py-3 font-medium">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {list.data.results.map((d) => (
                  <tr key={d.id} className="hover:bg-canvas">
                    <td className="px-5 py-3 font-mono text-xs whitespace-nowrap">
                      <Link to={`/documents/${d.id}`} className="text-electric hover:underline">{d.reference}</Link>
                    </td>
                    <td className="px-5 py-3">{d.document_label}{d.source === 'manual_mrz' && <span className="text-faint"> (typed)</span>}</td>
                    <td className="px-5 py-3">{d.holder || '—'}</td>
                    <td className="px-5 py-3 font-mono text-xs">{d.number || '—'}</td>
                    <td className="px-5 py-3 whitespace-nowrap text-muted">{formatDateTime(d.created_at)}</td>
                    <td className="px-5 py-3 whitespace-nowrap text-muted">{d.purged_at ? 'Deleted' : `On ${new Date(d.expires_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`}</td>
                    <td className="px-5 py-3"><StatusBadge status={d.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="mt-3 text-xs text-faint">Lists show only the surname's first letter and the last three characters of each number.</p>
      {pages > 1 && (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-muted">Page {page} of {pages}</span>
          <Button disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </>
  )
}

/* ---------------- Compare ---------------- */

function CompareTab() {
  const queryClient = useQueryClient()
  const [chosen, setChosen] = useState<number[]>([])
  const [result, setResult] = useState<Comparison | null>(null)
  const list = useQuery({
    queryKey: ['documents', 'list', 'active'],
    queryFn: () => api<Page<DocumentListItem>>('/api/documents/analyses/?active=1&page_size=100'),
  })
  const run = useMutation({
    mutationFn: () => api<Comparison>('/api/documents/comparisons/', { method: 'POST', body: { analysis_ids: chosen } }),
    onSuccess: (c) => { setResult(c); queryClient.invalidateQueries({ queryKey: ['documents', 'comparisons'] }) },
  })

  function toggle(id: number) {
    setResult(null)
    setChosen((current) => current.includes(id) ? current.filter((x) => x !== id) : current.length < 4 ? [...current, id] : current)
  }

  return (
    <div className="space-y-6">
      <Panel title="Choose 2 to 4 documents" aside={`${chosen.length} chosen`}>
        {list.isPending ? <Loading /> : !list.data?.results.length ? (
          <p className="text-sm text-muted">Analyse at least two documents first. Records whose data has been deleted can't be compared.</p>
        ) : (
          <>
            <ul className="divide-y divide-rule">
              {list.data.results.map((d) => (
                <li key={d.id}>
                  <label className="flex cursor-pointer items-center gap-3 py-2.5 text-sm">
                    <input type="checkbox" checked={chosen.includes(d.id)} onChange={() => toggle(d.id)}
                      disabled={!chosen.includes(d.id) && chosen.length >= 4} className="size-4 accent-electric" />
                    <span className="font-mono text-xs">{d.reference}</span>
                    <span>{d.document_label}</span>
                    <span className="text-muted">{d.holder} {d.number}</span>
                    <span className="ml-auto"><StatusBadge status={d.status} /></span>
                  </label>
                </li>
              ))}
            </ul>
            {run.isError && <div className="mt-3"><Notice tone="error">{run.error.message}</Notice></div>}
            <Button variant="primary" className="mt-4" disabled={chosen.length < 2 || run.isPending} onClick={() => run.mutate()}>
              {run.isPending ? 'Comparing…' : 'Compare documents'}
            </Button>
          </>
        )}
      </Panel>
      {result && <ComparisonResult comparison={result} />}
    </div>
  )
}

function ComparisonResult({ comparison: c }: { comparison: Comparison }) {
  return (
    <Panel title={`Comparison ${c.reference}`} aside={<StatusBadge status={c.status} />}>
      <p className="mb-4 text-sm">{c.summary}</p>
      <div className="-mx-5 -mb-5 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-y border-rule text-muted">
            <tr>
              <th scope="col" className="px-5 py-3 font-medium">Field</th>
              {c.documents.map((d) => <th key={d.id} scope="col" className="px-5 py-3 font-medium">{d.document_label}<br /><span className="font-mono text-xs font-normal">{d.reference}</span></th>)}
              <th scope="col" className="px-5 py-3 font-medium">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {c.rows.map((row) => (
              <tr key={row.field} className="align-top">
                <th scope="row" className="px-5 py-3 font-medium">{row.label}</th>
                {c.documents.map((d) => (
                  <td key={d.id} className="px-5 py-3">{row.values?.find((v) => v.reference === d.reference)?.value || <span className="text-faint">—</span>}</td>
                ))}
                <td className="px-5 py-3">
                  <StatusBadge status={row.status} />
                  {row.reason && <p className="mt-1 max-w-64 text-xs text-muted">{row.reason}</p>}
                  {row.status !== 'PASS' && row.status !== 'NOT_CHECKED' && row.action && <p className="mt-1 max-w-64 text-xs">{row.action}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

/* ---------------- SSN ---------------- */

function SsnTab() {
  const queryClient = useQueryClient()
  const [number, setNumber] = useState('')
  const [result, setResult] = useState<SsnResult | null>(null)
  const history = useQuery({ queryKey: ['documents', 'ssn'], queryFn: () => api<Page<SsnResult>>('/api/documents/ssn-checks/') })
  const run = useMutation({
    mutationFn: (value: string) => api<SsnResult>('/api/documents/ssn-checks/', { method: 'POST', body: { number: value } }),
    onSuccess: (r) => { setResult(r); queryClient.invalidateQueries({ queryKey: ['documents', 'ssn'] }) },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const value = number
    setNumber('')  // the full number leaves the screen as soon as it's sent
    run.mutate(value)
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
      <div className="space-y-6">
        <Panel title="Check an SSN's format">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label htmlFor="ssn" className="mb-1.5 block text-sm font-medium">Social Security Number</label>
              <input id="ssn" value={number} onChange={(e) => setNumber(e.target.value)} inputMode="numeric" autoComplete="off"
                spellCheck={false} maxLength={11} placeholder="AAA-GG-SSSS" className={`${inputClass} h-10 max-w-xs tabular-nums`} />
              <p className="mt-1 text-xs text-faint">Cleared as soon as you check it. Only the last four digits are kept.</p>
            </div>
            {run.isError && <Notice tone="error">{run.error.message}</Notice>}
            <Button type="submit" variant="primary" disabled={!number.trim() || run.isPending}>{run.isPending ? 'Checking…' : 'Check format'}</Button>
          </form>
        </Panel>
        {result && (
          <Panel title={`Result for ${result.masked}`} aside={<StatusBadge status={result.status} />}>
            <p className={cx('mb-4 text-sm font-medium', result.format_valid ? 'text-pass' : 'text-fail')}>
              {result.format_valid ? 'The format is valid.' : 'The format is not valid.'}
            </p>
            <ul className="divide-y divide-rule">
              {result.checks.map((c) => (
                <li key={c.code} className="flex items-start justify-between gap-4 py-2.5 text-sm">
                  <span><span className="font-medium">{c.name}</span><span className="block text-xs text-muted">{c.detail}</span></span>
                  <StatusBadge status={c.status} />
                </li>
              ))}
            </ul>
            {result.statement && <p className="mt-4 text-xs text-muted">{result.statement}</p>}
          </Panel>
        )}
      </div>
      <Panel title="Recent checks">
        {!history.data?.results.length ? <p className="text-sm text-muted">No checks yet.</p> : (
          <ul className="divide-y divide-rule">
            {history.data.results.slice(0, 10).map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="font-mono">{h.masked}</span>
                <span className="text-xs text-muted">{formatDateTime(h.created_at)}</span>
                <StatusBadge status={h.status} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
