// Types for /api/documents/ - kept in step with apps/document_analysis on the backend.
import type { ResultStatus } from './analyzer'

export interface IdCheck {
  category: string
  code: string
  name: string
  status: ResultStatus
  detail?: string
  positions?: [number, number][]
}

export interface IdField {
  label: string
  value: string
  display: string
  source?: string
}

export interface MrzData {
  layout: 'TD1' | 'TD2' | 'TD3'
  lines: string[]
  original: string[]
  fields: Record<string, IdField>
  checks: IdCheck[]
  corrections: { line: number; index: number; found: string; used: string; reason: string }[]
  segments: { line: number; start: number; end: number; field: string }[]
  status: ResultStatus
}

export interface DocumentAnalysis {
  id: number
  reference: string
  created_at: string
  created_by: string | null
  source: 'upload' | 'manual_mrz'
  requested_type: string
  detected_type: string
  document_label: string
  status: ResultStatus
  summary: string
  next_action: string
  checks: IdCheck[]
  fields: Record<string, IdField>
  mrz: MrzData | null
  licence: { fields: Record<string, IdField>; checks: IdCheck[] } | null
  ocr: { page: number; text: string; mean_confidence: number; word_count: number; low_confidence: string[] }[]
  pages: { page: number; width: number; height: number; findings: { code: string; message: string }[] }[]
  warnings: string[]
  ocr_engine: string
  duration_ms: number
  authenticity: { status: ResultStatus; detail: string }
  upload: { original_name: string; kind: string; size_bytes: number; sha256: string; page_count: number; file_available: boolean } | null
  expires_at: string
  purged_at: string | null
  purge_reason: string
  links: { pages: string[] }
}

export interface DocumentListItem {
  id: number
  reference: string
  created_at: string
  created_by: string | null
  source: string
  detected_type: string
  document_label: string
  status: ResultStatus
  holder: string
  number: string
  expires_at: string
  purged_at: string | null
}

export interface ComparisonRow {
  field: string
  label: string
  status: ResultStatus
  values?: { reference: string; document_type: string; value: string }[]
  confidence?: number | null
  reason?: string
  action?: string
}

export interface Comparison {
  id: number
  reference: string
  created_at: string
  status: ResultStatus
  summary: string
  rows: ComparisonRow[]
  documents: { id: number; reference: string; document_label: string }[]
  expires_at: string
  purged_at: string | null
}

export interface SsnResult {
  id: number
  masked: string
  format_valid: boolean
  status: ResultStatus
  checks: IdCheck[]
  statement?: string
  created_at: string
}

export interface DocumentsMeta {
  types: { key: string; label: string }[]
  retention_days: number
  ocr: { available: boolean; engine: string }
}
