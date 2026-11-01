import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Health } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Loading, Notice, PageHeader, Panel } from '../components/ui'
import { StatusBadge } from '../components/StatusBadge'
import type { ResultStatus } from '../api/analyzer'

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-4 py-2.5 text-sm first:pt-0 last:pb-0">
      <dt className="text-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

export function SettingsPage() {
  const { user } = useAuth()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/api/health/') })

  return (
    <>
      <PageHeader title="Settings" description="Your account and the state of this DocumentLab installation." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Your account">
          {user && (
            <dl className="divide-y divide-rule">
              <Row label="Username" value={user.username} />
              <Row label="Name" value={[user.first_name, user.last_name].filter(Boolean).join(' ') || '—'} />
              <Row label="Email" value={user.email || '—'} />
              <Row label="Role" value={user.role_label} />
              <Row label="Last sign-in" value={user.last_login ? new Date(user.last_login).toLocaleString('en-GB') : '—'} />
            </dl>
          )}
          <p className="mt-4 text-xs text-faint">To change your name, role or password, ask an administrator.</p>
        </Panel>

        <Panel title="System">
          {health.isPending ? <Loading /> : (
            <dl className="divide-y divide-rule">
              <Row label="Server" value={health.isError
                ? <span className="text-fail">Not reachable</span>
                : <span className="text-pass">Running</span>} />
              <Row label="Database" value={health.data?.database === 'ok'
                ? <span className="text-pass">Connected</span>
                : <span className="text-fail">Unavailable</span>} />
              <Row label="Version" value={health.data?.version ?? '—'} />
              <Row label="API reference" value={<a className="text-electric hover:underline" href="/api/docs/" target="_blank" rel="noreferrer">Open the API docs</a>} />
            </dl>
          )}
        </Panel>
      </div>
      {user?.role === 'ADMINISTRATOR' && <SecurityStatus />}
    </>
  )
}

interface StatusItem { key: string; label: string; status: ResultStatus; detail: string; action: string }

function SecurityStatus() {
  const status = useQuery({ queryKey: ['system', 'status'], queryFn: () => api<{ status: ResultStatus; items: StatusItem[]; checked_at: string }>('/api/system/status/') })
  return (
    <Panel title="Security and readiness" className="mt-6" aside={status.data && <StatusBadge status={status.data.status} />}>
      {status.isPending ? <Loading /> : status.isError ? <Notice tone="error">{status.error.message}</Notice> : (
        <>
          <ul className="divide-y divide-rule">
            {status.data.items.map((item) => (
              <li key={item.key} className="flex items-start justify-between gap-4 py-3 first:pt-0">
                <div className="text-sm">
                  <span className="font-medium">{item.label}</span>
                  <span className="mt-0.5 block text-muted">{item.detail}</span>
                  {item.action && <span className="mt-1 block text-xs">{item.action}</span>}
                </div>
                <StatusBadge status={item.status} />
              </li>
            ))}
          </ul>
          <p className="mt-4 border-t border-rule pt-3 text-xs text-faint">
            Measured from this server's settings when the page loaded. Development mode always shows problems here;
            run with production settings (docs/DEPLOYMENT.md) for real use.
          </p>
        </>
      )}
    </Panel>
  )
}
