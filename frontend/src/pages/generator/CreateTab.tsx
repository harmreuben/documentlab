import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../api/client'
import type { BarcodeRequest, CheckResponse, FieldIssue, FormatInfo, FormatKey, GeneratedBarcode, PayloadSchema } from '../../api/generator'
import { useAuth } from '../../auth/AuthContext'
import { Button, Loading, Notice, Panel } from '../../components/ui'
import { useDebounced } from '../../hooks/useDebounced'
import { cx } from '../../lib/format'
import { OptionControl } from './OptionControl'
import { DownloadLinks, Field, FieldMessages, VerificationBadge, inputClass, issuesFor, useFormats } from './shared'

const TEXT_SCHEMA = 'documentlab.text.v1'

function defaultsFor(format: FormatInfo, keep: Record<string, unknown> = {}): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const spec of format.options) {
    values[spec.name] = spec.kind === 'colour' && keep[spec.name] ? keep[spec.name] : spec.default
  }
  return values
}

export function CreateTab() {
  const formats = useFormats()
  if (formats.isPending) return <Loading label="Loading formats" />
  if (formats.isError) return <Notice tone="error">{formats.error.message}</Notice>
  return <CreateForm formats={formats.data.formats} schemas={formats.data.schemas} />
}

function CreateForm({ formats, schemas }: { formats: FormatInfo[]; schemas: PayloadSchema[] }) {
  const { hasRole } = useAuth()
  const readOnly = hasRole('READ_ONLY')
  const queryClient = useQueryClient()

  const [formatKey, setFormatKey] = useState<FormatKey>('qr')
  const format = formats.find((f) => f.key === formatKey)!
  const [schemaId, setSchemaId] = useState(TEXT_SCHEMA)
  const schema = schemas.find((s) => s.id === schemaId)!
  const [payload, setPayload] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [options, setOptions] = useState<Record<string, unknown>>(() => defaultsFor(format))
  const [label, setLabel] = useState('')
  const [saved, setSaved] = useState<GeneratedBarcode | null>(null)
  const [refused, setRefused] = useState<FieldIssue[] | null>(null)

  function chooseFormat(next: FormatInfo) {
    setFormatKey(next.key)
    setOptions((current) => defaultsFor(next, current))
    if (!next.structured) setSchemaId(TEXT_SCHEMA)
    setSaved(null)
    setRefused(null)
  }

  const body: BarcodeRequest = useMemo(
    () => ({ format: formatKey, schema: schemaId, payload, fields: schema.structured ? fields : {}, options }),
    [formatKey, schemaId, payload, fields, options, schema.structured],
  )
  const settled = useDebounced(body)
  const hasInput = (b: BarcodeRequest) =>
    b.schema === TEXT_SCHEMA ? b.payload.trim() !== '' : Object.values(b.fields).some((v) => v.trim() !== '')

  const check = useQuery({
    queryKey: ['generator', 'check', settled],
    queryFn: () => api<CheckResponse>('/api/generator/check/', { method: 'POST', body: settled }),
    enabled: hasInput(settled),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
  const typing = body !== settled
  const live = hasInput(settled) ? check.data : undefined

  const sample = useMutation({
    mutationFn: () => api<{ payload?: string; fields?: Record<string, string> }>(
      `/api/generator/sample/?format=${formatKey}&schema=${encodeURIComponent(schemaId)}`),
    onSuccess: (data) => {
      if (data.payload !== undefined) setPayload(data.payload)
      if (data.fields) setFields(data.fields)
      setSaved(null)
    },
  })

  const create = useMutation({
    mutationFn: () => api<GeneratedBarcode>('/api/generator/barcodes/', { method: 'POST', body: { ...body, label } }),
    onSuccess: (record) => {
      setSaved(record)
      setRefused(null)
      queryClient.invalidateQueries({ queryKey: ['generator', 'history'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => {
      const details = error instanceof ApiError ? (error.details as { errors?: FieldIssue[] } | null) : null
      setRefused(details?.errors ?? [{ field: 'form', message: error.message }])
    },
  })

  const errors = refused ?? live?.errors ?? []
  const warnings = live?.warnings ?? []
  const canGenerate = !readOnly && hasInput(body) && !typing && !check.isFetching && live?.ok === true

  const payloadErrors = issuesFor(errors, 'payload')
  const isLinear = format.family === 'linear'

  return (
    <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      {/* ---------------- Form ---------------- */}
      <form className="space-y-8" onSubmit={(e) => { e.preventDefault(); if (canGenerate) create.mutate() }} noValidate>
        <fieldset>
          <legend className="mb-3 text-[0.95rem] font-semibold">Format</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {formats.map((f) => (
              <label key={f.key}
                className={cx('flex cursor-pointer gap-3 rounded-[10px] border bg-paper px-4 py-3',
                  'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-electric',
                  f.key === formatKey ? 'border-electric ring-1 ring-electric' : 'border-rule hover:border-[#B9C2CF]')}>
                <input type="radio" name="format" value={f.key} checked={f.key === formatKey}
                  onChange={() => chooseFormat(f)} className="sr-only"
                  aria-labelledby={`format-${f.key}-name`} aria-describedby={`format-${f.key}-summary`} />
                <span>
                  <span id={`format-${f.key}-name`} className="block text-sm font-medium">{f.name}</span>
                  <span id={`format-${f.key}-summary`} className="mt-0.5 block text-xs leading-snug text-muted">{f.summary}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-4">
          <legend className="mb-3 text-[0.95rem] font-semibold">Content</legend>

          {format.structured && (
            <Field id="schema" label="Payload layout" hint={schema.description}>
              <select id="schema" value={schemaId} onChange={(e) => { setSchemaId(e.target.value); setSaved(null) }}
                className={`${inputClass} h-9`}>
                {schemas.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
          )}

          {schema.structured ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {schema.fields.map((f) => {
                const id = `field-${f.name}`
                const fieldErrors = issuesFor(errors, f.name)
                const set = (value: string) => { setFields({ ...fields, [f.name]: value }); setSaved(null); setRefused(null) }
                return (
                  <Field key={f.name} id={id} label={f.required ? f.label : `${f.label} (optional)`} hint={f.pattern_hint}>
                    {f.kind === 'choice' ? (
                      <select id={id} value={fields[f.name] ?? ''} onChange={(e) => set(e.target.value)}
                        aria-invalid={fieldErrors.length > 0} className={`${inputClass} h-9`}>
                        <option value="">Choose…</option>
                        {f.choices?.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    ) : (
                      <input id={id} value={fields[f.name] ?? ''} onChange={(e) => set(e.target.value)}
                        type={f.kind === 'date' ? 'date' : 'text'}
                        inputMode={f.kind === 'integer' ? 'numeric' : f.kind === 'number' ? 'decimal' : undefined}
                        maxLength={f.max_length} aria-invalid={fieldErrors.length > 0} className={`${inputClass} h-9`} />
                    )}
                    <FieldMessages errors={fieldErrors} />
                  </Field>
                )
              })}
            </div>
          ) : (
            <Field id="payload" label="Data to encode"
              hint={format.digits
                ? `${format.digits[0]} digits, and the check digit is added for you. Or enter all ${format.digits[1]}.`
                : `Up to ${format.max_length.toLocaleString('en-GB')} characters.`}>
              {isLinear ? (
                <input id="payload" value={payload} spellCheck={false} autoComplete="off"
                  inputMode={format.digits ? 'numeric' : undefined}
                  onChange={(e) => { setPayload(e.target.value); setSaved(null); setRefused(null) }}
                  aria-invalid={payloadErrors.length > 0} aria-describedby="payload-messages"
                  className={`${inputClass} h-10 text-[0.95rem] tabular-nums`} />
              ) : (
                <textarea id="payload" value={payload} rows={4} spellCheck={false}
                  onChange={(e) => { setPayload(e.target.value); setSaved(null); setRefused(null) }}
                  aria-invalid={payloadErrors.length > 0} aria-describedby="payload-messages"
                  className={`${inputClass} py-2 text-[0.95rem]`} />
              )}
              <FieldMessages id="payload-messages" errors={payloadErrors} warnings={issuesFor(warnings, 'payload')} />
            </Field>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" onClick={() => sample.mutate()} disabled={sample.isPending}>Fill with sample data</Button>
            <span className="text-xs text-faint">Fictional values marked TEST. Retail numbers use ranges reserved for internal use.</span>
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-3 text-[0.95rem] font-semibold">Size and colour</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            {format.options.map((spec) => (
              <OptionControl key={`${format.family}-${spec.name}`} spec={spec} value={options[spec.name]}
                onChange={(value) => { setOptions({ ...options, [spec.name]: value }); setSaved(null); setRefused(null) }}
                errors={issuesFor(errors, spec.name)} warnings={issuesFor(warnings, spec.name)} />
            ))}
          </div>
          {format.notes.map((note) => <p key={note} className="mt-3 text-xs text-faint">{note}</p>)}
        </fieldset>

        <div className="space-y-4 border-t border-rule pt-6">
          <Field id="label" label="Label (optional)" hint="Shown in History and printed on the label sheet.">
            <input id="label" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} className={`${inputClass} h-9 sm:max-w-sm`} />
          </Field>
          {issuesFor(errors, 'format').concat(issuesFor(errors, 'schema'), issuesFor(errors, 'form')).map((m) => (
            <Notice key={m} tone="error">{m}</Notice>
          ))}
          {readOnly ? (
            <Notice>Your account is read-only, so you can preview barcodes but not save them.</Notice>
          ) : (
            <Button type="submit" variant="primary" className="h-10 px-5" disabled={!canGenerate || create.isPending}>
              {create.isPending ? 'Generating…' : 'Generate and verify'}
            </Button>
          )}
        </div>
      </form>

      {/* ---------------- Preview and result ---------------- */}
      <div className="space-y-4 xl:sticky xl:top-8">
        {saved && <SavedResult record={saved} />}
        {check.isError && <Notice tone="error">{check.error.message}</Notice>}
        <Preview format={format} live={live} hasInput={hasInput(body)} busy={typing || check.isFetching}
          blocked={Boolean(live?.blocked)} />
      </div>
    </div>
  )
}

function Preview({ format, live, hasInput, busy, blocked }: {
  format: FormatInfo; live: CheckResponse | undefined; hasInput: boolean; busy: boolean; blocked: boolean
}) {
  const verdict = live?.verification
  const details = live?.preview?.details ?? {}
  return (
    <Panel title="Preview" aside={hasInput && busy ? 'Checking…' : undefined}>
      <div className={cx('flex min-h-56 items-center justify-center rounded-md border border-rule bg-canvas p-6 transition-opacity',
        busy && live ? 'opacity-60' : '')}>
        {!hasInput ? (
          <p className="max-w-56 text-center text-sm text-muted">Enter data, or fill with sample data, to see the {format.name}.</p>
        ) : live?.preview ? (
          <img src={live.preview.svg_data_url} alt={`${format.name} preview`}
            className={format.family === 'linear' ? 'h-auto w-full max-w-[22rem]' : 'max-h-80 max-w-full'} />
        ) : blocked ? (
          <p className="max-w-64 text-center text-sm text-fail">Not generated. See the message under the data.</p>
        ) : live ? (
          <p className="max-w-56 text-center text-sm text-muted">Fix the highlighted fields to see a preview.</p>
        ) : (
          <p className="text-sm text-muted">Checking…</p>
        )}
      </div>

      {live?.ok && verdict && (
        <dl className="mt-5 space-y-3 text-sm">
          <div>
            <dt className="text-muted">A scanner will read</dt>
            <dd className="mt-1 font-mono text-[0.8rem] leading-relaxed break-all">{live.expected_decode}</dd>
          </div>
          {live.check_digit && (
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Check digit</dt>
              <dd className="tabular-nums">{live.check_digit} <span className="text-faint">(calculated)</span></dd>
            </div>
          )}
          {'qr_version' in details && (
            <div className="flex justify-between gap-4"><dt className="text-muted">QR version</dt><dd>{String(details.qr_version)}</dd></div>
          )}
          {'pdf417_rows' in details && (
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Size</dt>
              <dd>{String(details.pdf417_columns)} columns × {String(details.pdf417_rows)} rows</dd>
            </div>
          )}
          <div className="flex items-start justify-between gap-4 border-t border-rule pt-3">
            <dt className="text-muted">Decoder check</dt>
            <dd className="text-right">
              <VerificationBadge status={verdict.status} />
              <p className="mt-1 max-w-64 text-xs text-faint">{verdict.detail}</p>
            </dd>
          </div>
        </dl>
      )}
      {live?.warnings.filter((w) => !['payload'].includes(w.field)).length ? (
        <ul className="mt-4 space-y-1">
          {live.warnings.filter((w) => w.field !== 'payload').map((w) => (
            <li key={w.field + w.message} className="text-xs text-review">{w.message}</li>
          ))}
        </ul>
      ) : null}
    </Panel>
  )
}

function SavedResult({ record }: { record: GeneratedBarcode }) {
  return (
    <section aria-live="polite" className={cx('rounded-[10px] border bg-paper p-5',
      record.verification_status === 'PASS' ? 'border-[#BFE3D3]' : 'border-[#F1C4C7]')}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[0.95rem] font-semibold">
            {record.verification_status === 'PASS' ? 'Saved and verified' : 'Saved, but verification failed'}
          </h2>
          <p className="mt-0.5 font-mono text-sm">{record.test_reference}</p>
        </div>
        <VerificationBadge status={record.verification_status} />
      </div>
      {record.verification_status !== 'PASS' && <p className="mt-2 text-sm text-fail">{record.verification_detail}</p>}
      <div className="mt-4"><DownloadLinks links={record.downloads} /></div>
    </section>
  )
}
