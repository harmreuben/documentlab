import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { api } from '../../api/client'
import type { Queue } from '../../api/reviews'
import { useAuth } from '../../auth/AuthContext'
import { StatusBadge } from '../../components/StatusBadge'
import { Loading, Notice, PageHeader, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'

export function ReviewQueuePage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const decided = params.get('tab') === 'decided'
  const queue = useQuery({
    queryKey: ['reviews', decided ? 'decided' : 'pending'],
    queryFn: () => api<Queue>(`/api/reviews/${decided ? '?decided=1' : ''}`),
  })
  const reviewer = user?.role === 'ADMINISTRATOR' || user?.role === 'REVIEWER'

  return (
    <>
      <PageHeader title="Review Queue"
        description={reviewer
          ? 'Results that need a second person. Open each one, compare the flagged checks with the original, then confirm or reject it. You can\'t review your own analyses.'
          : 'Your results that are waiting for a reviewer, and the decisions made on them.'} />
      <div role="tablist" aria-label="Review views" className="mb-6 flex gap-1 border-b border-rule">
        {[['pending', `Waiting${queue.data && !decided ? ` (${queue.data.pending})` : ''}`], ['decided', 'Decided']].map(([key, label]) => (
          <button key={key} role="tab" type="button" aria-selected={(key === 'decided') === decided}
            onClick={() => setParams(key === 'decided' ? { tab: 'decided' } : {}, { replace: true })}
            className={cx('-mb-px border-b-2 px-4 py-2.5 text-sm',
              (key === 'decided') === decided ? 'border-electric font-medium text-ink' : 'border-transparent text-muted hover:text-ink')}>
            {label}
          </button>
        ))}
      </div>

      <Panel>
        {queue.isPending ? <Loading /> : queue.isError ? <Notice tone="error">{queue.error.message}</Notice>
          : queue.data.results.length === 0 ? (
            <p className="text-sm text-muted">{decided ? 'No decisions yet.' : 'Nothing is waiting for review.'}</p>
          ) : (
            <ul className="-mx-5 -my-5 divide-y divide-rule">
              {queue.data.results.map((item) => (
                <li key={`${item.kind}-${item.id}`} className="flex flex-wrap items-start gap-x-5 gap-y-2 px-5 py-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <Link to={item.path} className="font-mono text-xs text-electric hover:underline">{item.reference}</Link>
                      <span className="text-xs text-muted">{item.label}</span>
                      {item.own && reviewer && <span className="rounded border border-rule px-1.5 py-px text-[0.7rem] text-muted">Your analysis</span>}
                    </div>
                    <p className="mt-1 text-sm">{item.summary}</p>
                    <p className="mt-1 text-xs text-muted">
                      Analysed {formatDateTime(item.created_at)}{item.created_by ? ` by ${item.created_by}` : ''}
                      {decided && item.reviewed_by && ` · ${item.review_label} by ${item.reviewed_by}${item.reviewed_at ? `, ${formatDateTime(item.reviewed_at)}` : ''}`}
                    </p>
                    {decided && item.review_note && <p className="mt-1.5 text-xs">“{item.review_note}”</p>}
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={item.status} />
                    {decided ? (
                      <span className={cx('text-xs font-medium', item.review_state === 'CONFIRMED' ? 'text-pass' : item.review_state === 'REJECTED' ? 'text-fail' : 'text-muted')}>{item.review_label}</span>
                    ) : item.can_review ? (
                      <Link to={item.path} className="rounded-md bg-electric px-3 py-1.5 text-xs font-medium text-white hover:bg-electric/90">Review</Link>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
      </Panel>
    </>
  )
}
