import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { api } from '../../api/client'
import type { DocumentAnalysis, IdCheck } from '../../api/documents'
import { useAuth } from '../../auth/AuthContext'
import { ReviewPanel } from '../../components/ReviewPanel'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, Loading, Notice, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { MrzView } from './MrzView'

const CATEGORY_NAMES: Record<string, string> = {
  file_integrity: 'File', image_quality: 'Image quality', ocr: 'Text recognition', parsing: 'Reading the data',
  data_format: 'Data format and check digits', dates: 'Dates', consistency: 'Printed text vs encoded data',
  external: 'External verification',
}
const FIELD_ORDER = ['surname', 'given_names', 'document_number', 'birth_date', 'sex', 'nationality', 'issuing_state',
  'expiry_date', 'issue_date', 'document_type', 'optional_data']

function longDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

export function DocumentResultPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const record = useQuery({
    queryKey: ['documents', 'analysis', id],
    queryFn: () => api<DocumentAnalysis>(`/api/documents/analyses/${id}/`),
  })
  const remove = useMutation({
    mutationFn: () => api<DocumentAnalysis>(`/api/documents/analyses/${id}/delete-data/`, { method: 'POST' }),
    onSuccess: (r) => {
      queryClient.setQueryData(['documents', 'analysis', id], r)
      queryClient.invalidateQueries({ queryKey: ['documents', 'list'] })
    },
  })

  if (record.isPending) return <Loading label="Loading the document" />
  if (record.isError) return <Notice tone="error">{record.error.message.includes('404') ? "This record doesn't exist or isn't yours to view." : record.error.message}</Notice>
  const d = record.data
  const canDelete = !d.purged_at && (user?.username === d.created_by || user?.role === 'ADMINISTRATOR')
  const grouped = Object.entries(CATEGORY_NAMES)
    .map(([key, name]) => ({ key, name, checks: d.checks.filter((c) => c.category === key) }))
    .filter((g) => g.checks.length)
  const fieldKeys = [...FIELD_ORDER.filter((k) => d.fields[k]), ...Object.keys(d.fields).filter((k) => !FIELD_ORDER.includes(k) && !['first_name', 'middle_names'].includes(k))]

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-4 text-sm">
        <Link to="/documents?tab=records" className="text-muted hover:text-electric">Document Analysis</Link>
        <span className="mx-2 text-faint">/</span><span className="font-mono text-xs">{d.reference}</span>
      </nav>

      <header className={cx('mb-8 rounded-[10px] border bg-paper px-6 py-5', d.status === 'PASS' ? 'border-[#BFE3D3]' : d.status === 'FAIL' ? 'border-[#F1C4C7]' : d.status === 'REVIEW_REQUIRED' ? 'border-[#F3D5A8]' : 'border-rule')}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <p className="text-sm text-muted">{d.document_label}{d.source === 'manual_mrz' ? ', typed MRZ' : ''}</p>
            <h1 className="mt-1 text-[1.5rem] leading-tight font-semibold tracking-[-0.01em]">{d.summary}</h1>
            <p className="mt-2 text-[0.95rem] text-muted"><span className="font-medium text-ink">Next: </span>{d.next_action}</p>
          </div>
          <StatusBadge status={d.status} large />
        </div>
        <p className="mt-4 border-t border-rule pt-3 text-xs text-muted">
          <span className="font-medium text-ink">Authenticity not checked.</span> {d.authenticity.detail}
        </p>
      </header>

      {d.purged_at ? (
        <div className="space-y-6">
          <Notice>Personal data was deleted on {longDate(d.purged_at)} ({d.purge_reason}). Only the reference, document type and check results remain.</Notice>
          <ReviewPanel kind="document" id={d.id} createdBy={d.created_by} review={d.review} purged queryKey={['documents', 'analysis', id]} />
        </div>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <div className="space-y-6">
            {d.mrz && (
              <Panel title={`Machine-readable zone (${d.mrz.layout})`} aside={<StatusBadge status={d.mrz.status} />}>
                <MrzView mrz={d.mrz} />
              </Panel>
            )}
            <Panel title="Extracted fields">
              {fieldKeys.length === 0 ? <p className="text-sm text-muted">No fields could be extracted.</p> : (
                <dl className="divide-y divide-rule text-sm">
                  {fieldKeys.map((k) => (
                    <div key={k} className="grid grid-cols-[9rem_1fr_auto] gap-3 py-2.5">
                      <dt className="text-muted">{d.fields[k].label}</dt>
                      <dd className="font-medium break-all">{d.fields[k].display || '—'}</dd>
                      <dd className="text-xs text-faint">{d.fields[k].source}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </Panel>
            {d.links.pages.map((src, i) => (
              <Panel key={src} title={d.links.pages.length > 1 ? `Page ${i + 1}` : 'Image'}>
                <img src={src} alt={`Page ${i + 1} of the uploaded document`} className="w-full rounded-md border border-rule" />
              </Panel>
            ))}
            {d.ocr.length > 0 && (
              <Panel title="Recognised text">
                {d.ocr.map((o) => (
                  <details key={o.page} className="text-sm">
                    <summary className="cursor-pointer">
                      {d.ocr.length > 1 ? `Page ${o.page}: ` : ''}{o.word_count} words, average confidence {Math.round(o.mean_confidence)}%
                    </summary>
                    <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-canvas p-3 font-mono text-xs whitespace-pre-wrap">{o.text || '(none)'}</pre>
                    {o.low_confidence.length > 0 && <p className="mt-2 text-xs text-review">Low confidence: {o.low_confidence.join(', ')}</p>}
                  </details>
                ))}
              </Panel>
            )}
          </div>

          <div className="space-y-6">
            <Panel title="Checks">
              <div className="space-y-5">
                {grouped.map((g) => (
                  <section key={g.key}>
                    <h3 className="mb-1.5 text-xs font-medium text-muted">{g.name}</h3>
                    <ul className="divide-y divide-rule">
                      {g.checks.map((c: IdCheck, i) => (
                        <li key={c.code + i} className="flex items-start justify-between gap-4 py-2.5">
                          <span className="text-sm"><span className="font-medium">{c.name}</span>
                            {c.detail && <span className="mt-0.5 block text-xs leading-relaxed text-muted">{c.detail}</span>}</span>
                          <StatusBadge status={c.status} />
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            </Panel>
            <ReviewPanel kind="document" id={d.id} createdBy={d.created_by} review={d.review} queryKey={['documents', 'analysis', id]} />
            <Panel title="Record" aside={<a href={d.links.pdf} download className="text-xs font-medium text-electric hover:underline">PDF report</a>}>
              <dl className="space-y-2 text-sm">
                <div className="grid grid-cols-[7rem_1fr] gap-3"><dt className="text-muted">Analysed</dt><dd>{formatDateTime(d.created_at)}{d.created_by ? ` by ${d.created_by}` : ''}</dd></div>
                {d.upload && <div className="grid grid-cols-[7rem_1fr] gap-3"><dt className="text-muted">File</dt><dd className="break-all">{d.upload.original_name} ({d.upload.kind.toUpperCase()})</dd></div>}
                {d.ocr_engine && <div className="grid grid-cols-[7rem_1fr] gap-3"><dt className="text-muted">OCR</dt><dd>{d.ocr_engine}</dd></div>}
                <div className="grid grid-cols-[7rem_1fr] gap-3"><dt className="text-muted">Rule set</dt><dd>{d.ruleset_version || 'Before rule versioning'}</dd></div>
                <div className="grid grid-cols-[7rem_1fr] gap-3"><dt className="text-muted">Data deleted</dt><dd>{longDate(d.expires_at)}</dd></div>
              </dl>
              <p className="mt-3 text-xs text-faint">The PDF report includes this document's personal data and is marked confidential.</p>
              {canDelete && (
                <div className="mt-4 border-t border-rule pt-4">
                  {remove.isError && <div className="mb-3"><Notice tone="error">{remove.error.message}</Notice></div>}
                  <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
                    {remove.isPending ? 'Deleting…' : 'Delete personal data now'}
                  </Button>
                  <p className="mt-2 text-xs text-faint">Removes the image, fields and text. The reference and check results stay for the audit trail.</p>
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}
    </>
  )
}
