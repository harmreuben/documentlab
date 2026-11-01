import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import { ROLE_LABELS, type DashboardSummary, type Role } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { visibleNavigation } from '../navigation'
import { Figure, Loading, Notice, PageHeader, Panel } from '../components/ui'
import { actionLabel, cx, formatDateTime } from '../lib/format'

function plural(n: number, word: string): string {
  return `${n.toLocaleString('en-GB')} ${word}${n === 1 ? '' : 's'}`
}

function shortDay(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export function DashboardPage() {
  const { user } = useAuth()
  const summary = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api<DashboardSummary>('/api/dashboard/summary/'),
    refetchInterval: 60_000,
  })

  if (summary.isPending) return <Loading label="Loading the dashboard" />
  if (summary.isError) return <Notice tone="error">{summary.error.message}</Notice>

  const data = summary.data
  const system = data.scope === 'system'
  const totalActivity = data.activity.reduce((sum, d) => sum + d.events, 0)
  // Only list modules this user can open.
  const navItems = visibleNavigation(user?.role).flatMap((g) => g.items)
  const modules = data.modules.filter((m) => navItems.some((item) => item.key === m.key))

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user?.first_name || user?.username}`}
        description={system
          ? 'System-wide activity across every account.'
          : 'Your own activity. Administrators see figures for the whole system.'}
      />

      <div className={cx('grid gap-4 sm:grid-cols-2', system ? 'xl:grid-cols-4' : 'xl:grid-cols-3')}>
        <Figure label="Events in the last 24 hours" value={data.counts.events_24h} />
        <Figure label="Sign-ins in the last 7 days" value={data.counts.logins_7d} />
        {system && <Figure label="Failed sign-ins in the last 7 days" value={data.counts.failed_logins_7d} />}
        {system && data.users
          ? <Figure label="Active users" value={data.users.active} note={`${data.users.total} accounts in total`} />
          : <Figure label="Pending reviews" value={data.counts.pending_reviews} note="Arrives with review workflows" />}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Figure label="Barcodes generated" value={data.counts.barcodes_generated}
          note={data.counts.barcodes_generated === null
            ? 'Arrives with the Barcode Generator'
            : `${data.counts.barcodes_failed_verification ?? 0} failed verification`} />
        <Figure label="Barcodes decoded" value={data.counts.barcodes_decoded}
          note={data.counts.barcodes_decoded === null ? 'Arrives with the Barcode Analyzer' : undefined} />
        <Figure label="Documents processed" value={data.counts.documents_processed}
          note={data.counts.documents_processed === null ? 'Arrives with Document Analysis' : undefined} />
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel title="Activity, last 14 days" aside={plural(totalActivity, 'event')}>
          <div className="h-64" role="img" aria-label={`Bar chart of audit events per day: ${plural(totalActivity, 'event')} over 14 days.`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.activity} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                <CartesianGrid vertical={false} stroke="#EDF0F4" />
                <XAxis dataKey="date" tickFormatter={shortDay} tick={{ fontSize: 12, fill: '#5B6678' }}
                  axisLine={{ stroke: '#DCE1E8' }} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#5B6678' }} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: '#F3F5F8' }} labelFormatter={(d) => shortDay(String(d))}
                  formatter={(v) => [v, 'Events']} contentStyle={{ borderRadius: 6, borderColor: '#DCE1E8', fontSize: 13 }} />
                <Bar dataKey="events" fill="#1F5BFF" radius={[3, 3, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Recent activity" aside={system && <Link className="text-electric hover:underline" to="/audit">Open the audit log</Link>}>
          {data.recent_activity.length === 0 ? (
            <p className="text-sm text-muted">No activity recorded yet.</p>
          ) : (
            <ul className="divide-y divide-rule">
              {data.recent_activity.map((event) => (
                <li key={event.id} className="flex items-baseline justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <span className="text-sm">
                    <span className="font-medium">{event.username || 'Unknown user'}</span>{' '}
                    <span className={cx(event.action === 'auth.login_failed' ? 'text-fail' : 'text-muted')}>
                      {actionLabel(event.action).toLowerCase()}
                    </span>
                  </span>
                  <time className="shrink-0 text-xs text-faint" dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className={cx('mt-6 grid gap-6', system && 'xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]')}>
        <Panel title="Modules" aside={`Version ${data.version}`}>
          <ul className="grid gap-x-8 sm:grid-cols-2">
            {modules.map((module) => {
              const nav = navItems.find((item) => item.key === module.key)
              const ready = module.status === 'available'
              return (
                <li key={module.key} className="flex items-center justify-between gap-3 border-b border-rule py-2.5">
                  {nav ? <Link to={nav.path} className="text-sm hover:text-electric">{module.name}</Link> : <span className="text-sm">{module.name}</span>}
                  <span className={cx('text-xs', ready ? 'text-pass' : 'text-faint')}>
                    {ready ? 'Ready' : `Phase ${module.phase}`}
                  </span>
                </li>
              )
            })}
          </ul>
        </Panel>

        {system && data.users && (
          <Panel title="Active users by role">
            <dl className="divide-y divide-rule">
              {(Object.keys(ROLE_LABELS) as Role[]).map((role) => (
                <div key={role} className="flex justify-between py-2.5 text-sm first:pt-0 last:pb-0">
                  <dt className="text-muted">{ROLE_LABELS[role]}</dt>
                  <dd className="font-medium tabular-nums">{data.users!.by_role[role]}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        )}
      </div>
    </>
  )
}
