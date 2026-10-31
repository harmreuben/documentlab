import { useSearchParams } from 'react-router'
import { PageHeader } from '../../components/ui'
import { cx } from '../../lib/format'
import { BatchTab } from './BatchTab'
import { CreateTab } from './CreateTab'
import { HistoryTab } from './HistoryTab'

const TABS = [
  { key: 'create', label: 'Create' },
  { key: 'batch', label: 'Batch from CSV' },
  { key: 'history', label: 'History' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function GeneratorPage() {
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.key === params.get('tab'))?.key ?? 'create') as TabKey

  return (
    <>
      <PageHeader
        title="Barcode Generator"
        description="Create generic barcodes and neutral test data. Before anything is saved, a separate reader decodes the image and compares it with what you asked for."
      />

      <div role="tablist" aria-label="Generator views" className="mb-6 flex gap-1 border-b border-rule">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            onClick={() => setParams(t.key === 'create' ? {} : { tab: t.key }, { replace: true })}
            className={cx(
              '-mb-px border-b-2 px-4 py-2.5 text-sm',
              tab === t.key ? 'border-electric font-medium text-ink' : 'border-transparent text-muted hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'create' && <CreateTab />}
        {tab === 'batch' && <BatchTab />}
        {tab === 'history' && <HistoryTab />}
      </div>
    </>
  )
}
