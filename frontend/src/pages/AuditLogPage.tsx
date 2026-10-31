import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AuditEvent, Page } from '../api/types'
import { Button, Loading, Notice, PageHeader, Panel } from '../components/ui'
import { ACTION_LABELS, actionLabel, cx } from '../lib/format'

export function AuditLogPage() {
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [username, setUsername] = useState('')

  const params = new URLSearchParams({ page: String(page) })
  if (action) params.set('action', action)
  if (username.trim()) params.set('username', username.trim())

  const events = useQuery({
    queryKey: ['audit', page, action, username.trim()],
    queryFn: () => api<Page<AuditEvent>>(`/api/audit/events/?${params}`),
    placeholderData: keepPreviousData,
  })

  const pageCount = events.data ? Math.max(1, Math.ceil(events.data.count / 25)) : 1

  return (
    <>
      <PageHeader title="Audit log" description="Every sign-in and account change, newest first. Entries cannot be edited or deleted." />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Action</span>
          <select value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }}
            className="h-9 rounded-md border border-rule bg-paper px-2.5">
            <option value="">All actions</option>
            {Object.entries(ACTION_LABELS).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Username</span>
          <input value={username} onChange={(e) => { setUsername(e.target.value); setPage(1) }} placeholder="Exact username"
            className="h-9 w-48 rounded-md border border-rule bg-paper px-2.5" />
        </label>
      </div>

      <Panel title="Events" aside={events.data && `${events.data.count.toLocaleString('en-GB')} matching`}>
        {events.isPending ? <Loading /> : events.isError ? <Notice tone="error">{events.error.message}</Notice> : (
          events.data.results.length === 0 ? <p className="text-sm text-muted">No events match these filters.</p> : (
            <div className="-mx-5 -my-5 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-rule text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-medium">When</th>
                    <th scope="col" className="px-5 py-3 font-medium">User</th>
                    <th scope="col" className="px-5 py-3 font-medium">Action</th>
                    <th scope="col" className="px-5 py-3 font-medium">Details</th>
                    <th scope="col" className="px-5 py-3 font-medium">IP address</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {events.data.results.map((e) => (
                    <tr key={e.id} className="align-top">
                      <td className="px-5 py-3 whitespace-nowrap tabular-nums text-muted">
                        {new Date(e.created_at).toLocaleString('en-GB')}
                      </td>
                      <td className="px-5 py-3 font-medium">{e.username || '—'}</td>
                      <td className={cx('px-5 py-3', e.action === 'auth.login_failed' && 'text-fail')}>{actionLabel(e.action)}</td>
                      <td className="max-w-xs px-5 py-3 font-mono text-xs break-all text-muted">
                        {Object.keys(e.metadata).length ? JSON.stringify(e.metadata) : e.object_type ? `${e.object_type} ${e.object_id}` : '—'}
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-muted">{e.ip_address ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Panel>

      {events.data && pageCount > 1 && (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-muted">Page {page} of {pageCount}</span>
          <Button disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </>
  )
}
