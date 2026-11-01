import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router'
import { api, apiUpload } from '../../api/client'
import type { Analysis } from '../../api/analyzer'
import { useAuth } from '../../auth/AuthContext'
import { Button, Notice, PageHeader, Panel } from '../../components/ui'
import { cx } from '../../lib/format'
import { inputClass } from '../generator/shared'
import { HistoryList } from './HistoryList'

const ACCEPT = '.png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf'

function size(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}

export function AnalyzerPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'history' ? 'history' : 'analyse'
  const tabs = [{ key: 'analyse', label: 'Analyse' }, { key: 'history', label: 'History' }] as const

  return (
    <>
      <PageHeader
        title="Barcode Analyzer"
        description="Upload a photo, scan or PDF. Every barcode in it is decoded, checked against its format's rules and judged for image quality. Uncertain reads are marked for review, never passed."
      />
      <div role="tablist" aria-label="Analyzer views" className="mb-6 flex gap-1 border-b border-rule">
        {tabs.map((t) => (
          <button key={t.key} role="tab" type="button" aria-selected={tab === t.key}
            onClick={() => setParams(t.key === 'analyse' ? {} : { tab: t.key }, { replace: true })}
            className={cx('-mb-px border-b-2 px-4 py-2.5 text-sm',
              tab === t.key ? 'border-electric font-medium text-ink' : 'border-transparent text-muted hover:text-ink')}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'analyse' ? <AnalyseTab /> : <HistoryList />}
    </>
  )
}

function AnalyseTab() {
  const { hasRole } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [expected, setExpected] = useState('')
  const [dragging, setDragging] = useState(false)
  const [reference, setReference] = useState('')

  const done = (analysis: Analysis) => {
    queryClient.invalidateQueries({ queryKey: ['analyzer'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.setQueryData(['analyzer', 'analysis', String(analysis.id)], analysis)
    navigate(`/analyzer/${analysis.id}`)
  }

  const analyseFile = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.append('file', file!)
      if (expected.trim()) form.append('expected', expected.trim())
      return apiUpload<Analysis>('/api/analyzer/analyses/', form)
    },
    onSuccess: done,
  })

  const analyseGenerated = useMutation({
    mutationFn: () => api<Analysis>('/api/analyzer/analyses/from-generated/', {
      method: 'POST', body: { test_reference: reference.trim() },
    }),
    onSuccess: done,
  })

  if (hasRole('READ_ONLY')) {
    return <Notice>Your account is read-only, so you can't upload files. Previous analyses are on the History tab.</Notice>
  }

  function choose(chosen: File | undefined | null) {
    setFile(chosen ?? null)
    analyseFile.reset()
  }

  function drop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    choose(event.dataTransfer.files?.[0])
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (file) analyseFile.mutate()
  }

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <Panel title="Upload a file">
        <form onSubmit={submit} className="space-y-5">
          <label htmlFor="analyse-file"
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
            className={cx('flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-[10px] border-2 border-dashed px-6 py-8 text-center',
              'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-electric',
              dragging ? 'border-electric bg-electric-soft' : 'border-rule bg-canvas hover:border-[#B9C2CF]')}>
            <input ref={input} id="analyse-file" type="file" accept={ACCEPT} className="sr-only"
              onChange={(e) => choose(e.target.files?.[0])} />
            {file ? (
              <>
                <span className="text-sm font-medium break-all">{file.name}</span>
                <span className="mt-1 text-xs text-muted">{size(file.size)}. Click or drop to choose a different file.</span>
              </>
            ) : (
              <>
                <span className="text-sm font-medium">Drop a file here, or click to choose one</span>
                <span className="mt-1 text-xs text-muted">PNG, JPEG or PDF, up to 10 MB. PDFs: the first 10 pages.</span>
              </>
            )}
          </label>

          <div>
            <label htmlFor="expected" className="mb-1.5 block text-sm font-medium">Expected value (optional)</label>
            <input id="expected" value={expected} onChange={(e) => setExpected(e.target.value)} spellCheck={false}
              className={`${inputClass} h-9`} />
            <p className="mt-1 text-xs text-faint">If you know what the barcode should contain, the result says whether it matches exactly.</p>
          </div>

          {analyseFile.isError && <Notice tone="error">{analyseFile.error.message}</Notice>}
          <Button type="submit" variant="primary" className="h-10 px-5" disabled={!file || analyseFile.isPending}>
            {analyseFile.isPending ? 'Analysing…' : 'Analyse file'}
          </Button>
        </form>
      </Panel>

      <div className="space-y-6">
        <Panel title="Check a generated barcode">
          <form onSubmit={(e) => { e.preventDefault(); if (reference.trim()) analyseGenerated.mutate() }} className="space-y-3">
            <p className="text-sm text-muted">Analyse a barcode from the Generator using its saved image. The value it was made with is used as the expected value.</p>
            <label htmlFor="generated-ref" className="block text-sm font-medium">Test reference</label>
            <div className="flex gap-2">
              <input id="generated-ref" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="GEN-…"
                className={`${inputClass} h-9 uppercase`} spellCheck={false} />
              <Button type="submit" disabled={!reference.trim() || analyseGenerated.isPending}>
                {analyseGenerated.isPending ? 'Analysing…' : 'Analyse barcode'}
              </Button>
            </div>
            {analyseGenerated.isError && <Notice tone="error">{analyseGenerated.error.message}</Notice>}
          </form>
        </Panel>

        <Panel title="What is checked">
          <dl className="space-y-2.5 text-sm">
            {[
              ['File', 'Its real type, from the content rather than the name.'],
              ['Image quality', 'Size, sharpness, contrast and exposure, with the measured values.'],
              ['Decoding', 'Every barcode found, read again at two other scales to confirm the result.'],
              ['Data format', 'Check digits and DocumentLab schemas, where they apply.'],
              ['Expected value', 'An exact match, if you entered one.'],
            ].map(([term, text]) => (
              <div key={term}><dt className="font-medium">{term}</dt><dd className="text-muted">{text}</dd></div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-faint">These are technical checks. A barcode that decodes cleanly is not proof that a document is genuine.</p>
        </Panel>
      </div>
    </div>
  )
}
