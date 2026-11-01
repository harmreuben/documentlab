// Types for /api/analyzer/ - kept in step with apps/barcode_decoder on the backend.
import type { ReviewInfo } from './reviews'

export type ResultStatus = 'PASS' | 'FAIL' | 'REVIEW_REQUIRED' | 'NOT_SUPPORTED' | 'UNAVAILABLE' | 'NOT_CHECKED'

export interface Check {
  category: 'file_integrity' | 'image_quality' | 'barcode_decoding' | 'data_format' | 'expected_value'
  status: ResultStatus
  detail: string
}

export interface PageQuality {
  page: number
  width: number
  height: number
  sharpness: number
  contrast_range: number
  mean_brightness: number
  findings: { code: string; message: string }[]
}

export interface Interpretation {
  kind: string
  summary: string
  data_check: ResultStatus
  data_detail: string
  fields: { label: string; value: string }[]
  notes: string[]
  sensitive: boolean
}

export interface DecodedBarcode {
  id: number
  page: number
  index: number
  format_name: string
  format_key: string
  supported: boolean
  text: string | null
  byte_length: number
  valid: boolean
  error: string
  points: [number, number][]
  tilt: number
  ec_level: string
  symbology_identifier: string
  consistent_reads: number
  attempts: number
  alternatives: Record<string, string>
  interpretation: Interpretation
  findings: { code: string; message: string }[]
  expected_match: boolean | null
  status: ResultStatus
  reason: string
  matched_generated: { id: number; test_reference: string; format: string; created_at: string; verification_status: string } | null
}

export interface Analysis {
  id: number
  reference: string
  created_at: string
  created_by: string | null
  upload: {
    original_name: string
    kind: 'png' | 'jpeg' | 'pdf'
    size_bytes: number
    sha256: string
    page_count: number
    file_available: boolean
    file_removed_reason: string
  }
  source_generated: string | null
  expected_value: string
  status: ResultStatus
  summary: string
  next_action: string
  checks: Check[]
  pages: PageQuality[]
  warnings: string[]
  sensitive: boolean
  duration_ms: number
  decoder: string
  barcodes: DecodedBarcode[]
  ruleset_version: string
  review: ReviewInfo
  links: { json: string; csv: string; pdf: string; pages?: string[] }
}

export interface AnalysisListItem {
  id: number
  reference: string
  created_at: string
  created_by: string | null
  file_name: string
  file_kind: string
  status: ResultStatus
  summary: string
  barcode_count: number
  formats: string[]
  sensitive: boolean
}
