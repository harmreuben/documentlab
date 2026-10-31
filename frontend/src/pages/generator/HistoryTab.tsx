import { Fragment, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { GeneratedBarcode } from '../../api/generator'
import type { Page } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Button, Loading, Notice, Panel } from '../../components/ui'
import { useDebounced } from '../../hooks/useDebounced'
import { formatDateTime } from '../../lib/format'
import { DownloadLinks, VerificationBadge, inputClass, useFormats } from './shared'

export function HistoryTab() {
  const { hasRole } = useAuth()
  const admin = hasRole('ADMINISTRATOR')
  const formats = useFormats()
  const [format, setFormat] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const term = useDebounced(search.trim())

  const params = new URLSearchParams({ page: String(page) })
  if (format) params.set('format', format)
  if (status) params.set('status', status)
  if (term) params.set('search', term)

  const history = useQuery({
    queryKey: ['generator', 'history', format, status, term, page],
    queryFn: () => api<Page<GeneratedBarcode>>(`/api/generator/barcodes/?${params}`),
    placeholderData: keepPreviousData,
  })
  const pages = history.data ? Math.max(1, Math.ceil(history.data.count / 25)) : 1
  const names = Object.fromEntries((formats.data?.formats ?? []).map((f) => [f.key, f.name]))
  const schemaNames = Object.fromEntries((formats.data?.schemas ?? []).map((s) => [s.id, s.name]))
  const columns = admin ? 7 : 6

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Format</span>
          <select value={format} onChange={(e) => { setFormat(e.target.value); setPage(1) }} className={`${inputClass} h-9 w-40`}>
            <option value="">All formats</option>
            {formats.data?.formats.map((f) => <option key={f.key} value={f.key}>{f.name}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Verification</span>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className={`${inputClass} h-9 w-40`}>
            <option value="">Any result</option>
            <option value="PASS">Pass</option>
            <option value="FAIL">Fail</option>
            <option value="UNAVAILABLE">Not checked</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Reference or label</span>
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} placeholder="GEN-…"
            className={`${inputClass} h-9 w-56`} />
        </label>
      </div>

      <Panel title="Generated barcodes" aside={history.data && `${history.data.count.toLocaleString('en-GB')} found`}>
        {history.isPending ? <Loading /> : history.isError ? <Notice tone="error">{history.error.message}</Notice> : (
          history.data.results.length === 0 ? (
            <p className="text-sm text-muted">{format || status || term ? 'Nothing matches these filters.' : 'No barcodes yet. Create one on the Create tab.'}</p>
          ) : (
            <div className="-mx-5 -my-5 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-rule text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-medium">Reference</th>
                    <th scope="col" className="px-5 py-3 font-medium">Format</th>
                    <th scope="col" className="px-5 py-3 font-medium">Label</th>
                    <th scope="col" className="px-5 py-3 font-medium">Created</th>
                    {admin && <th scope="col" className="px-5 py-3 font-medium">By</th>}
                    <th scope="col" className="px-5 py-3 font-medium">Verification</th>
                    <th scope="col" className="px-5 py-3"><span className="sr-only">Details</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {history.data.results.map((b) => (
                    <Fragment key={b.id}>
                      <tr>
                        <td className="px-5 py-3 font-mono text-xs whitespace-nowrap">{b.test_reference}</td>
                        <td className="px-5 py-3 whitespace-nowrap">{names[b.format] ?? b.format}</td>
                        <td className="px-5 py-3">{b.label || <span className="text-faint">—</span>}</td>
                        <td className="px-5 py-3 whitespace-nowrap text-muted">{formatDateTime(b.created_at)}</td>
                        {admin && <td className="px-5 py-3">{b.created_by ?? '—'}</td>}
                        <td className="px-5 py-3"><VerificationBadge status={b.verification_status} /></td>
                        <td className="px-5 py-3 text-right">
                          <Button type="button" className="h-7 px-2 text-xs" aria-expanded={open === b.id}
                            onClick={() => setOpen(open === b.id ? null : b.id)}>
                            {open === b.id ? 'Hide' : 'Details'}
                          </Button>
                        </td>
                      </tr>
                      {open === b.id && (
                        <tr className="bg-canvas">
                          <td colSpan={columns} className="px-5 py-4">
                            <dl className="grid gap-x-8 gap-y-3 text-sm md:grid-cols-2">
                              <div className="md:col-span-2">
                                <dt className="text-muted">Encoded data (what a scanner reads)</dt>
                                <dd className="mt-1 font-mono text-xs break-all">{b.expected_decode}</dd>
                              </div>
                              <div><dt className="text-muted">Payload layout</dt><dd>{schemaNames[b.schema_id] ?? b.schema_id}</dd></div>
                              <div><dt className="text-muted">Image size</dt><dd className="tabular-nums">{b.width_px} × {b.height_px} px</dd></div>
                              <div><dt className="text-muted">Decoder result</dt><dd>{b.verification_detail}</dd></div>
                              <div><dt className="text-muted">Downloads</dt><dd className="tabular-nums">{b.download_count}</dd></div>
                              <div className="md:col-span-2">
                                <dt className="text-muted">PNG fingerprint (SHA-256)</dt>
                                <dd className="mt-1 font-mono text-xs break-all text-muted">{b.png_sha256}</dd>
                              </div>
                            </dl>
                            <div className="mt-4"><DownloadLinks links={b.downloads} /></div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Panel>

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
