import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiUpload } from '../../api/client'
import type { GenerationBatch } from '../../api/generator'
import type { Page } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Button, Figure, Notice, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { DownloadLinks, VerificationBadge } from './shared'

// Example rows use fictional data only. Retail numbers start with 2 or 4 (ranges for internal use).
const TEMPLATE = [
  'format,payload,label,schema,asset_id,name,location,acquired',
  'qr,https://example.test/items/TEST-0001,Shelf QR,,,,,',
  'code128,DL-TEST-000001,Bin label,,,,,',
  'code39,TEST-00001,,,,,,',
  'ean13,200000000001,Internal product,,,,,',
  'ean8,2000001,,,,,,',
  'upca,40000000001,,,,,,',
  'pdf417,,Asset tag,documentlab.asset-tag.v1,TEST-AST-0001,Bench scanner,Lab bench 2,2026-01-15',
].join('\r\n')

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob(['﻿' + TEMPLATE], { type: 'text/csv;charset=utf-8' }))
  const link = Object.assign(document.createElement('a'), { href: url, download: 'documentlab-batch-template.csv' })
  link.click()
  URL.revokeObjectURL(url)
}

export function BatchTab() {
  const { hasRole } = useAuth()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [current, setCurrent] = useState<GenerationBatch | null>(null)

  const previous = useQuery({
    queryKey: ['generator', 'batches'],
    queryFn: () => api<Page<GenerationBatch>>('/api/generator/batches/'),
  })

  const run = useMutation({
    mutationFn: (chosen: File) => {
      const form = new FormData()
      form.append('file', chosen)
      return apiUpload<GenerationBatch>('/api/generator/batches/', form)
    },
    onSuccess: (batch) => {
      setCurrent(batch)
      setFile(null)
      if (input.current) input.current.value = ''
      queryClient.invalidateQueries({ queryKey: ['generator'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (hasRole('READ_ONLY')) {
    return <Notice>Your account is read-only, so you can't run batches. You can still open previous batches in History.</Notice>
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel title="Upload a CSV">
          <form onSubmit={(e) => { e.preventDefault(); if (file) run.mutate(file) }} className="space-y-4">
            <div>
              <label htmlFor="batch-file" className="mb-1.5 block text-sm font-medium">CSV file</label>
              <input ref={input} id="batch-file" type="file" accept=".csv,text/csv"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); run.reset() }}
                className="block w-full text-sm file:mr-3 file:h-9 file:rounded-md file:border file:border-rule file:bg-paper file:px-3.5 file:text-sm file:font-medium hover:file:bg-canvas" />
              <p className="mt-1 text-xs text-faint">Up to 500 rows and 1 MB. Each row is checked on its own, so one bad row doesn't stop the rest.</p>
            </div>
            {run.isError && <Notice tone="error">{run.error.message}</Notice>}
            <Button type="submit" variant="primary" disabled={!file || run.isPending}>
              {run.isPending ? 'Generating and verifying…' : 'Generate batch'}
            </Button>
          </form>
        </Panel>

        <Panel title="File layout">
          <ul className="space-y-2 text-sm text-muted">
            <li><span className="font-medium text-ink">format</span>: qr, code128, code39, ean13, ean8, upca or pdf417</li>
            <li><span className="font-medium text-ink">payload</span>: the text to encode</li>
            <li><span className="font-medium text-ink">label</span>: optional name for the label</li>
            <li><span className="font-medium text-ink">schema</span>: optional; for structured QR or PDF417 rows, plus one column per schema field</li>
          </ul>
          <p className="mt-3 text-sm text-muted">Every barcode uses the default size and colours for its format.</p>
          <Button type="button" className="mt-4" onClick={downloadTemplate}>Download the template</Button>
        </Panel>
      </div>

      {current && <BatchResult batch={current} />}

      <Panel title="Previous batches">
        {previous.data?.results.length ? (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-rule text-muted">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">File</th>
                  <th scope="col" className="px-5 py-3 font-medium">When</th>
                  <th scope="col" className="px-5 py-3 text-right font-medium">Rows</th>
                  <th scope="col" className="px-5 py-3 text-right font-medium">Generated</th>
                  <th scope="col" className="px-5 py-3 text-right font-medium">Rejected</th>
                  <th scope="col" className="px-5 py-3"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {previous.data.results.map((b) => (
                  <tr key={b.id}>
                    <td className="px-5 py-3 font-medium">{b.source_name}</td>
                    <td className="px-5 py-3 whitespace-nowrap text-muted">{formatDateTime(b.created_at)}</td>
                    <td className="px-5 py-3 text-right tabular-nums">{b.total_rows}</td>
                    <td className="px-5 py-3 text-right tabular-nums">{b.succeeded}</td>
                    <td className={cx('px-5 py-3 text-right tabular-nums', b.failed > 0 && 'text-fail')}>{b.failed}</td>
                    <td className="px-5 py-3 text-right">
                      <Button type="button" className="h-7 px-2 text-xs" onClick={() => setCurrent(b)}>Show rows</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted">{previous.isPending ? 'Loading…' : 'No batches yet.'}</p>
        )}
      </Panel>
    </div>
  )
}

function BatchResult({ batch }: { batch: GenerationBatch }) {
  const failedVerification = batch.report.filter((r) => r.verification === 'FAIL').length
  return (
    <section aria-live="polite" className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <Figure label="Rows read" value={batch.total_rows} note={batch.source_name} />
        <Figure label="Generated and verified" value={batch.succeeded - failedVerification} />
        <Figure label="Rejected or failed" value={batch.failed + failedVerification} />
      </div>
      <Panel title={`Batch ${batch.id}: rows`} aside={batch.succeeded > 0 && <DownloadLinks links={batch.downloads} compact />}>
        <div className="-mx-5 -my-5 max-h-[28rem] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 border-b border-rule bg-paper text-muted">
              <tr>
                <th scope="col" className="px-5 py-3 font-medium">Row</th>
                <th scope="col" className="px-5 py-3 font-medium">Format</th>
                <th scope="col" className="px-5 py-3 font-medium">Label</th>
                <th scope="col" className="px-5 py-3 font-medium">Result</th>
                <th scope="col" className="px-5 py-3 font-medium">Reference or reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {batch.report.map((row) => (
                <tr key={row.row} className="align-top">
                  <td className="px-5 py-2.5 tabular-nums text-muted">{row.row}</td>
                  <td className="px-5 py-2.5">{row.format || '—'}</td>
                  <td className="px-5 py-2.5">{row.label || '—'}</td>
                  <td className="px-5 py-2.5">
                    {row.status === 'REJECTED'
                      ? <span className="text-xs font-medium text-fail">Rejected</span>
                      : row.verification && <VerificationBadge status={row.verification} />}
                  </td>
                  <td className="px-5 py-2.5">
                    {row.status === 'REJECTED'
                      ? <span className="text-fail">{row.message}</span>
                      : <span className="font-mono text-xs">{row.test_reference}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  )
}
