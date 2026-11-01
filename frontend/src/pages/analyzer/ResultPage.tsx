import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { api } from '../../api/client'
import type { Analysis, Check, DecodedBarcode } from '../../api/analyzer'
import { STATUS, StatusBadge } from '../../components/StatusBadge'
import { Loading, Notice, Panel } from '../../components/ui'
import { cx, formatDateTime } from '../../lib/format'
import { DownloadLinks } from '../generator/shared'

const CHECK_NAMES: Record<Check['category'], string> = {
  file_integrity: 'File',
  image_quality: 'Image quality',
  barcode_decoding: 'Decoding',
  data_format: 'Data format',
  expected_value: 'Expected value',
}

function bytes(n: number): string {
  return n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`
}

export function ResultPage() {
  const { id } = useParams()
  const analysis = useQuery({
    queryKey: ['analyzer', 'analysis', id],
    queryFn: () => api<Analysis>(`/api/analyzer/analyses/${id}/`),
  })
  const [selected, setSelected] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState<number | null>(null)

  if (analysis.isPending) return <Loading label="Loading the analysis" />
  if (analysis.isError) {
    return <Notice tone="error">{analysis.error.message === 'The server returned an error (404).'
      ? "This analysis doesn't exist or isn't yours to view." : analysis.error.message}</Notice>
  }

  const a = analysis.data
  const firstPageWithCodes = a.barcodes[0]?.page ?? a.pages[0]?.page ?? 1
  const page = pageNumber ?? firstPageWithCodes

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-4 text-sm">
        <Link to="/analyzer?tab=history" className="text-muted hover:text-electric">Barcode Analyzer</Link>
        <span className="mx-2 text-faint">/</span>
        <span className="font-mono text-xs">{a.reference}</span>
      </nav>

      <header className={cx('mb-8 rounded-[10px] border bg-paper px-6 py-5', {
        PASS: 'border-[#BFE3D3]', FAIL: 'border-[#F1C4C7]', REVIEW_REQUIRED: 'border-[#F3D5A8]',
      }[a.status as 'PASS' | 'FAIL' | 'REVIEW_REQUIRED'] ?? 'border-rule')}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <h1 className="text-[1.6rem] leading-tight font-semibold tracking-[-0.01em]">{a.summary}</h1>
            <p className="mt-2 text-[0.95rem] text-muted"><span className="font-medium text-ink">Next: </span>{a.next_action}</p>
          </div>
          <StatusBadge status={a.status} large />
        </div>
      </header>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <PageViewer analysis={a} page={page} onPage={setPageNumber} selected={selected} onSelect={setSelected} />

        <div className="space-y-6">
          <Panel title="Checks">
            <ul className="divide-y divide-rule">
              {a.checks.map((c) => (
                <li key={c.category} className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
                  <div>
                    <div className="text-sm font-medium">{CHECK_NAMES[c.category]}</div>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted">{c.detail}</p>
                  </div>
                  <StatusBadge status={c.status} />
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="File" aside={<DownloadLinks links={{ json: a.links.json, csv: a.links.csv }} compact />}>
            <dl className="space-y-2.5 text-sm">
              <Row label="Name" value={<span className="break-all">{a.upload.original_name}</span>} />
              <Row label="Type" value={`${a.upload.kind.toUpperCase()}, ${bytes(a.upload.size_bytes)}${a.upload.kind === 'pdf' ? `, ${a.upload.page_count} page${a.upload.page_count > 1 ? 's' : ''}` : ''}`} />
              <Row label="SHA-256" value={<span className="font-mono text-xs break-all text-muted">{a.upload.sha256}</span>} />
              {a.expected_value && <Row label="Expected" value={<span className="font-mono text-xs break-all">{a.expected_value}</span>} />}
              {a.source_generated && <Row label="Source" value={`Generated barcode ${a.source_generated}`} />}
              <Row label="Analysed" value={`${formatDateTime(a.created_at)}${a.created_by ? ` by ${a.created_by}` : ''}, in ${a.duration_ms} ms`} />
              <Row label="Decoder" value={a.decoder} />
            </dl>
            {a.warnings.length > 0 && (
              <ul className="mt-4 space-y-1">{a.warnings.map((w) => <li key={w} className="text-xs text-review">{w}</li>)}</ul>
            )}
          </Panel>
        </div>
      </div>

      <section className="mt-8">
        <h2 className="mb-4 text-[1.1rem] font-semibold">
          {a.barcodes.length ? `Barcodes found (${a.barcodes.length})` : 'No barcodes found'}
        </h2>
        {a.barcodes.length === 0 ? (
          <p className="text-sm text-muted">Nothing in this file could be read as a barcode. The image-quality check above explains the likely cause.</p>
        ) : (
          <ol className="space-y-4">
            {a.barcodes.map((b, i) => (
              <BarcodeCard key={b.id} number={i + 1} barcode={b} multiPage={a.pages.length > 1}
                selected={selected === b.id}
                onSelect={() => { setSelected(selected === b.id ? null : b.id); setPageNumber(b.page) }} />
            ))}
          </ol>
        )}
      </section>
    </>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-3">
      <dt className="text-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function PageViewer({ analysis, page, onPage, selected, onSelect }: {
  analysis: Analysis; page: number; onPage: (n: number) => void; selected: number | null; onSelect: (id: number | null) => void
}) {
  const info = analysis.pages.find((p) => p.page === page)
  const codes = analysis.barcodes.filter((b) => b.page === page)
  const numbered = new Map(analysis.barcodes.map((b, i) => [b.id, i + 1]))
  const src = analysis.links.pages?.find((url) => url.endsWith(`page=${page}`))

  return (
    <Panel title={analysis.pages.length > 1 ? `Page ${page} of ${analysis.pages.length} analysed` : 'Image'}
      aside={analysis.pages.length > 1 && (
        <div className="flex gap-1">
          {analysis.pages.map((p) => (
            <button key={p.page} type="button" onClick={() => onPage(p.page)} aria-pressed={p.page === page}
              aria-label={`Show page ${p.page}`}
              className={cx('h-7 min-w-7 rounded-md border px-2 text-xs tabular-nums',
                p.page === page ? 'border-electric bg-electric-soft text-ink' : 'border-rule hover:bg-canvas')}>
              {p.page}
            </button>
          ))}
        </div>
      )}>
      {!analysis.upload.file_available ? (
        <div className="flex min-h-56 items-center justify-center rounded-md border border-rule bg-canvas p-6 text-center">
          <p className="max-w-sm text-sm text-muted">{analysis.upload.file_removed_reason || 'The image is no longer stored.'}</p>
        </div>
      ) : info && src ? (
        <figure>
          <div className="relative overflow-hidden rounded-md border border-rule bg-canvas">
            <img src={src} alt={`Page ${page} of ${analysis.upload.original_name}`} className="block h-auto w-full" />
            <svg viewBox={`0 0 ${info.width} ${info.height}`} className="absolute inset-0 h-full w-full" aria-hidden="true">
              {codes.map((b) => {
                const stroke = STATUS[b.status].stroke
                const active = selected === b.id
                const [x, y] = b.points[0]
                const w = Math.max(info.width, info.height) / 400  // keeps outlines visible on any image size
                return (
                  <g key={b.id} className="cursor-pointer" onClick={() => onSelect(active ? null : b.id)}>
                    <polygon points={b.points.map((p) => p.join(',')).join(' ')} fill={stroke} fillOpacity={active ? 0.18 : 0.06}
                      stroke={stroke} strokeWidth={(active ? 3 : 2) * w} strokeLinejoin="round" />
                    <circle cx={x} cy={y} r={11 * w} fill={stroke} />
                    <text x={x} y={y + 4 * w} textAnchor="middle" fontSize={12 * w} fontWeight="600" fill="#fff">
                      {numbered.get(b.id)}
                    </text>
                  </g>
                )
              })}
            </svg>
          </div>
          <figcaption className="mt-3 text-xs text-muted">
            {codes.length
              ? 'Numbered outlines mark each barcode found. Select one to highlight its details below.'
              : 'No barcode was found on this page.'}
          </figcaption>
        </figure>
      ) : (
        <p className="text-sm text-muted">No image for this page.</p>
      )}

      {info && (
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
          <div><dt className="text-muted">Size</dt><dd className="tabular-nums">{info.width} × {info.height} px</dd></div>
          <div><dt className="text-muted">Sharpness</dt><dd className="tabular-nums">{Math.round(info.sharpness).toLocaleString('en-GB')}</dd></div>
          <div><dt className="text-muted">Contrast range</dt><dd className="tabular-nums">{info.contrast_range.toFixed(2)}</dd></div>
          <div><dt className="text-muted">Brightness</dt><dd className="tabular-nums">{info.mean_brightness.toFixed(2)}</dd></div>
        </dl>
      )}
      {info?.findings.length ? (
        <ul className="mt-3 space-y-1">{info.findings.map((f) => <li key={f.code} className="text-xs text-review">{f.message}</li>)}</ul>
      ) : null}
    </Panel>
  )
}

function BarcodeCard({ number, barcode: b, multiPage, selected, onSelect }: {
  number: number; barcode: DecodedBarcode; multiPage: boolean; selected: boolean; onSelect: () => void
}) {
  const meaning = b.interpretation
  return (
    <li className={cx('rounded-[10px] border bg-paper', selected ? 'border-electric ring-1 ring-electric' : 'border-rule')}>
      <button type="button" onClick={onSelect} aria-expanded={selected}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left">
        <span className="flex items-start gap-3">
          <span className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{ background: STATUS[b.status].stroke }}>{number}</span>
          <span>
            <span className="block text-sm font-medium">
              {b.format_name}{multiPage && <span className="font-normal text-muted">, page {b.page}</span>}
            </span>
            <span className="mt-0.5 block text-sm text-muted">{b.reason}</span>
          </span>
        </span>
        <StatusBadge status={b.status} />
      </button>

      <div className="grid gap-6 border-t border-rule px-5 py-4 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-medium text-muted">Decoded data</h3>
          {b.text === null ? (
            <p className="mt-1.5 text-sm text-review">Withheld. {meaning.data_detail}</p>
          ) : b.valid ? (
            <p className="mt-1.5 font-mono text-[0.8rem] leading-relaxed break-all">{b.text}</p>
          ) : (
            <p className="mt-1.5 text-sm text-fail">Not decoded{b.error ? `: ${b.error}` : ''}.</p>
          )}
          {Object.entries(b.alternatives).map(([key, value]) => (
            <p key={key} className="mt-2 text-xs text-muted">
              {key === 'code39_standard' ? 'Read as standard Code 39: ' : `${key}: `}
              <span className="font-mono text-ink">{value}</span>
            </p>
          ))}
          {b.expected_match !== null && (
            <p className={cx('mt-2 text-xs font-medium', b.expected_match ? 'text-pass' : 'text-fail')}>
              {b.expected_match ? 'Matches the expected value.' : 'Does not match the expected value.'}
            </p>
          )}
          {b.matched_generated && (
            <p className="mt-2 text-xs text-muted">
              Same data as generated barcode{' '}
              <Link className="font-mono text-electric hover:underline" to={`/generator?tab=history`}>{b.matched_generated.test_reference}</Link>.
            </p>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-medium text-muted">{meaning.summary}</h3>
            {meaning.data_check !== 'NOT_CHECKED' && <StatusBadge status={meaning.data_check} />}
          </div>
          {meaning.data_detail && b.text !== null && <p className="mt-1.5 text-sm">{meaning.data_detail}</p>}
          {meaning.fields.length > 0 && (
            <dl className="mt-2 divide-y divide-rule text-sm">
              {meaning.fields.map((f) => (
                <div key={f.label} className="flex justify-between gap-4 py-1.5">
                  <dt className="text-muted">{f.label}</dt><dd className="text-right break-all">{f.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {meaning.notes.map((n) => <p key={n} className="mt-2 text-xs text-faint">{n}</p>)}
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-8 gap-y-2 border-t border-rule px-5 py-3 text-xs">
        <div className="flex gap-1.5"><dt className="text-muted">Consistent reads</dt>
          <dd className={cx('tabular-nums', b.consistent_reads < b.attempts && 'text-review')}>{b.consistent_reads} of {b.attempts}</dd></div>
        <div className="flex gap-1.5"><dt className="text-muted">Tilt</dt><dd className="tabular-nums">{b.tilt}°</dd></div>
        {b.ec_level && <div className="flex gap-1.5"><dt className="text-muted">Error correction</dt><dd>{b.ec_level}</dd></div>}
        <div className="flex gap-1.5"><dt className="text-muted">Data size</dt><dd className="tabular-nums">{b.byte_length} bytes</dd></div>
      </dl>
      {b.findings.length > 0 && (
        <ul className="space-y-1 border-t border-rule px-5 py-3">
          {b.findings.map((f) => <li key={f.code} className="text-xs text-review">{f.message}</li>)}
        </ul>
      )}
    </li>
  )
}
