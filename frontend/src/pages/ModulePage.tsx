import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { DashboardSummary } from '../api/types'
import type { NavItem } from '../navigation'
import { PageHeader, Panel } from '../components/ui'

/**
 * Shown for a module whose phase is not finished. It says plainly that the module
 * does not work yet; it never shows controls that do nothing.
 */
export function ModulePage({ item }: { item: NavItem }) {
  const summary = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api<DashboardSummary>('/api/dashboard/summary/'),
  })
  const phase = summary.data?.modules.find((m) => m.key === item.key)?.phase

  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <Panel>
        <div className="flex items-start gap-4">
          <item.icon size={22} strokeWidth={1.5} className="mt-0.5 shrink-0 text-faint" aria-hidden="true" />
          <div>
            <p className="font-medium">This workspace is not built yet.</p>
            <p className="mt-1 text-sm text-muted">
              {phase ? `It arrives in Phase ${phase}. ` : ''}
              Until then nothing here can be run, so no results are shown.
            </p>
          </div>
        </div>
      </Panel>
    </>
  )
}
