import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { AnalysisListItem } from '../../api/analyzer'
import type { Page } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Loading, Notice, Panel } from '../../components/ui'
import { useDebounced } from '../../hooks/useDebounced'
import { formatDateTime } from '../../lib/format'
import { inputClass } from '../generator/shared'

export function HistoryList() {
  const { hasRole } = useAuth()
  const admin = hasRole('ADMINISTRATOR')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const term = useDebounced(search.trim())

  const params = new URLSearchParams({ page: String(page) })
  if (status) params.set('status', status)
  if (term) params.set('search', term)

  const list = useQuery({
    queryKey: ['analyzer', 'history', status, term, page],
    queryFn: () => api<Page<AnalysisListItem>>(`/api/analyzer/analyses/?${params}`),
    placeholderData: keepPreviousData,
  })
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / 25)) : 1

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Result</span>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className={`${inputClass} h-9 w-44`}>
            <option value="">Any result</option>
            <option value="PASS">Pass</option>
            <option value="FAIL">Fail</option>
            <option value="REVIEW_REQUIRED">Needs review</option>
            <option value="NOT_SUPPORTED">Not supported</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Reference or file name</span>
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} placeholder="ANA-…"
            className={`${inputClass} h-9 w-60`} />
        </label>
      </div>

      <Panel title="Analyses" aside={list.data && `${list.data.count.toLocaleString('en-GB')} found`}>
        {list.isPending ? <Loading /> : list.isError ? <Notice tone="error">{list.error.message}</Notice> : (
          list.data.results.length === 0 ? (
            <p className="text-sm text-muted">{status || term ? 'Nothing matches these filters.' : 'No analyses yet. Upload a file on the Analyse tab.'}</p>
          ) : (
            <div className="-mx-5 -my-5 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-rule text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-medium">Reference</th>
                    <th scope="col" className="px-5 py-3 font-medium">File</th>
                    <th scope="col" className="px-5 py-3 font-medium">Barcodes</th>
                    <th scope="col" className="px-5 py-3 font-medium">When</th>
                    {admin && <th scope="col" className="px-5 py-3 font-medium">By</th>}
                    <th scope="col" className="px-5 py-3 font-medium">Result</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {list.data.results.map((a) => (
                    <tr key={a.id} className="hover:bg-canvas">
                      <td className="px-5 py-3 font-mono text-xs whitespace-nowrap">
                        <Link to={`/analyzer/${a.id}`} className="text-electric hover:underline">{a.reference}</Link>
                      </td>
                      <td className="max-w-56 truncate px-5 py-3" title={a.file_name}>{a.file_name}</td>
                      <td className="px-5 py-3 text-muted">{a.barcode_count ? a.formats.join(', ') : 'None read'}</td>
                      <td className="px-5 py-3 whitespace-nowrap text-muted">{formatDateTime(a.created_at)}</td>
                      {admin && <td className="px-5 py-3">{a.created_by ?? '—'}</td>}
                      <td className="px-5 py-3"><StatusBadge status={a.status} /></td>
                    </tr>
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
