// Types for /api/test-lab/ - kept in step with apps/test_lab on the backend.
import type { ResultStatus } from './analyzer'

export type Module = 'analyzer' | 'documents'
export type Outcome = 'PASS' | 'FAIL' | 'ERROR'
export type Change = 'new' | 'unchanged' | 'new_failure' | 'fixed' | 'still_failing'

export interface Expectation {
  status?: ResultStatus[]
  checks?: Record<string, ResultStatus[]>
  max_duration_ms?: number
  barcode_count?: number
  barcodes?: { format: string; text?: string }[]
  detected_type?: string
  fields?: Record<string, string>
}

export interface Fixture {
  id: number
  name: string
  description: string
  module: Module
  module_label: string
  tags: string[]
  is_builtin: boolean
  builtin_key: string | null
  input_type: 'file' | 'mrz_text'
  original_name: string
  file_kind: string
  size_bytes: number
  mrz_text: string
  options: { expected_value?: string; document_type?: string }
  expected: Expectation
  active: boolean
  created_by: string | null
  created_at: string
  updated_at: string
  last_result: { outcome: Outcome; run_id: number; run_reference: string; at: string } | null
  links: { file: string | null }
}

export interface ComparisonRow {
  label: string
  expected: string
  actual: string
  passed: boolean
}

export interface CaseResult {
  id: number
  fixture: number | null
  position: number
  fixture_name: string
  module: Module
  outcome: Outcome
  change: Change
  previous_outcome: string
  expected: Expectation
  actual: { status: ResultStatus; summary: string; duration_ms: number } & Record<string, unknown> | null
  comparisons: ComparisonRow[]
  error: string
  duration_ms: number
}

export interface TestRun {
  id: number
  reference: string
  status: 'RUNNING' | 'COMPLETE' | 'INTERRUPTED'
  scope: { module?: Module; tag?: string; fixture_ids?: number[] }
  note: string
  total: number
  done: number
  passed: number
  failed: number
  errors: number
  new_failures: number
  fixed: number
  versions: { app?: string; decoder?: string; ocr?: string }
  baseline: { id: number; reference: string } | null
  created_by: string | null
  created_at: string
  finished_at: string | null
  duration_ms: number
}

export interface TestRunDetail extends TestRun {
  cases: CaseResult[]
  links: { json: string; csv: string; junit: string }
}

export interface TestLabMeta {
  modules: { key: Module; label: string }[]
  tags: string[]
  builtin_count: number
  builtin_loaded: number
  fixtures_active: number
  versions: { app: string; decoder: string; ocr: string }
  can_edit_fixtures: boolean
  can_add_document_images: boolean
  can_run: boolean
}
