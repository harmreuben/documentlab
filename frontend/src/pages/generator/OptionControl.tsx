import type { OptionSpec } from '../../api/generator'
import { FieldMessages, inputClass } from './shared'

interface Props {
  spec: OptionSpec
  value: unknown
  onChange: (value: unknown) => void
  errors: string[]
  warnings: string[]
}

/** One rendering option, drawn from the spec the backend sends (so limits live in one place). */
export function OptionControl({ spec, value, onChange, errors, warnings }: Props) {
  const id = `option-${spec.name}`
  const describedBy = errors.length || warnings.length ? `${id}-messages` : undefined
  const invalid = errors.length > 0

  if (spec.kind === 'boolean') {
    return (
      <div className="sm:col-span-2">
        <label htmlFor={id} className="flex items-center gap-2.5 text-sm">
          <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)}
            className="size-4 accent-electric" />
          {spec.label}
        </label>
        <FieldMessages id={describedBy} errors={errors} warnings={warnings} />
      </div>
    )
  }

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium">
        {spec.label}
        {spec.unit && <span className="font-normal text-faint"> ({spec.unit})</span>}
      </label>

      {spec.kind === 'choice' && (
        <select id={id} value={String(value)} onChange={(e) => onChange(e.target.value)}
          aria-invalid={invalid} aria-describedby={describedBy} className={`${inputClass} h-9`}>
          {spec.choices?.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      )}

      {(spec.kind === 'number' || spec.kind === 'integer') && (
        <input id={id} type="number" inputMode={spec.kind === 'integer' ? 'numeric' : 'decimal'}
          min={spec.minimum} max={spec.maximum} step={spec.step ?? (spec.kind === 'integer' ? 1 : 'any')}
          value={value === '' || value === undefined ? '' : String(value)}
          onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          aria-invalid={invalid} aria-describedby={describedBy} className={`${inputClass} h-9 tabular-nums`} />
      )}

      {spec.kind === 'colour' && (
        <div className="flex gap-2">
          <input type="color" aria-label={`${spec.label} picker`} value={String(value)}
            onChange={(e) => onChange(e.target.value.toUpperCase())}
            className="h-9 w-11 shrink-0 cursor-pointer rounded-md border border-rule bg-paper p-1" />
          <input id={id} value={String(value)} onChange={(e) => onChange(e.target.value)} spellCheck={false}
            aria-invalid={invalid} aria-describedby={describedBy} className={`${inputClass} h-9 uppercase tabular-nums`} />
        </div>
      )}

      {spec.help && !errors.length && <p className="mt-1 text-xs text-faint">{spec.help}</p>}
      <FieldMessages id={describedBy} errors={errors} warnings={warnings} />
    </div>
  )
}
