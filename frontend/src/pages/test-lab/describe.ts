import type { Expectation } from '../../api/testlab'
import { STATUS } from '../../components/StatusBadge'

function statusWords(values: string[]) {
  return values.map((v) => STATUS[v as keyof typeof STATUS]?.label ?? v).join(' or ')
}

/** The expectation written out in words, one line per rule. */
export function describeExpectation(e: Expectation): string[] {
  const lines: string[] = []
  if (e.status) lines.push(`Result: ${statusWords(e.status)}`)
  if (e.barcode_count !== undefined) lines.push(`${e.barcode_count} barcode${e.barcode_count === 1 ? '' : 's'} found`)
  for (const b of e.barcodes ?? []) lines.push(b.text !== undefined ? `${b.format} reading "${b.text}"` : `A ${b.format} is found`)
  if (e.detected_type) lines.push(`Detected as: ${e.detected_type.replace('_', ' ')}`)
  for (const [k, v] of Object.entries(e.fields ?? {})) lines.push(`${k.replace('_', ' ')} = ${v}`)
  for (const [k, v] of Object.entries(e.checks ?? {})) lines.push(`${k}: ${statusWords(v)}`)
  if (e.max_duration_ms) lines.push(`Takes at most ${e.max_duration_ms} ms`)
  return lines
}

export function moduleLabel(module: string) {
  return module === 'analyzer' ? 'Barcode Analyzer' : 'Document Analysis'
}

export function duration(ms: number) {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}
