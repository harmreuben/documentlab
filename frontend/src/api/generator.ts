// Types for /api/generator/ - kept in step with apps/barcode_generator on the backend.

export type FormatKey = 'qr' | 'code128' | 'code39' | 'ean13' | 'ean8' | 'upca' | 'pdf417'
export type Verification = 'PASS' | 'FAIL' | 'UNAVAILABLE'

export interface OptionSpec {
  name: string
  label: string
  kind: 'number' | 'integer' | 'choice' | 'colour' | 'boolean'
  default: number | string | boolean
  minimum?: number
  maximum?: number
  step?: number
  unit?: string
  choices?: { value: string; label: string }[]
  help?: string
}

export interface FormatInfo {
  key: FormatKey
  name: string
  family: 'linear' | 'matrix' | 'stacked'
  summary: string
  max_length: number
  structured: boolean
  digits: [number, number] | null
  notes: string[]
  options: OptionSpec[]
}

export interface SchemaField {
  name: string
  label: string
  kind?: 'text' | 'integer' | 'number' | 'date' | 'choice'
  required?: boolean
  max_length?: number
  pattern_hint?: string
  choices?: string[]
  minimum?: number
  maximum?: number
}

export interface PayloadSchema {
  id: string
  name: string
  description: string
  structured: boolean
  fields: SchemaField[]
}

export interface FormatsResponse {
  formats: FormatInfo[]
  schemas: PayloadSchema[]
  default_schema: string
}

export interface FieldIssue {
  field: string
  message: string
}

export interface CheckResponse {
  ok: boolean
  format: string
  schema: string
  expected_decode: string
  check_digit: string | null
  options: Record<string, unknown>
  errors: FieldIssue[]
  warnings: FieldIssue[]
  blocked: boolean
  preview: { svg_data_url: string; width: number; height: number; details: Record<string, unknown> } | null
  verification: { status: Verification; decoded_text: string | null; decoded_format: string | null; detail: string } | null
}

export interface BarcodeRequest {
  format: FormatKey
  schema: string
  payload: string
  fields: Record<string, string>
  options: Record<string, unknown>
  label?: string
}

export interface GeneratedBarcode {
  id: number
  test_reference: string
  created_at: string
  created_by: string | null
  batch: number | null
  batch_row: number | null
  format: FormatKey
  schema_id: string
  label: string
  input_payload: string
  input_fields: Record<string, string>
  expected_decode: string
  check_digit: string
  options: Record<string, unknown>
  render_details: Record<string, unknown>
  warnings: FieldIssue[]
  png_sha256: string
  width_px: number
  height_px: number
  verification_status: Verification
  decoded_text: string | null
  decoded_format: string
  verification_detail: string
  download_count: number
  last_downloaded_at: string | null
  downloads: { png: string; svg: string; pdf: string }
}

export interface BatchRow {
  row: number
  format: string
  schema: string
  label: string
  status: 'GENERATED' | 'REJECTED'
  test_reference: string
  verification: Verification | ''
  expected_decode: string
  message: string
}

export interface GenerationBatch {
  id: number
  created_at: string
  created_by: string | null
  source_name: string
  total_rows: number
  succeeded: number
  failed: number
  report: BatchRow[]
  downloads: { zip: string; pdf: string; csv: string }
}
