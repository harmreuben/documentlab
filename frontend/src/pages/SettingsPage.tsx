import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Health } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Loading, PageHeader, Panel } from '../components/ui'

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
    </>
  )
}
