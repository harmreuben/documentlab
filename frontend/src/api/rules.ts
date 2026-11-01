// Types for /api/rules/ - kept in step with core/rules on the backend.
import type { ResultStatus } from './analyzer'

export type CoverageLevel = 'full' | 'partial' | 'none' | 'outside'

export interface Rule {
  code: string
  name: string
  module: string
  module_label: string
  category: string
  checks: string
  outcomes: Partial<Record<ResultStatus, string>>
  reference: string
  version: number
  since: string
  changes: { version: number; app_version: string; note: string }[]
  parameters: Record<string, string>
  keys: string[]
  severity: 'blocking' | 'review' | 'information'
  severity_label: string
  coverage: {
    level: CoverageLevel
    label: string
    statuses: ResultStatus[]
    exercised_by: { id: number; name: string; statuses: ResultStatus[] }[]
    asserted_by: { id: number; name: string }[]
  }
}

export interface RulesResponse {
  ruleset_version: string
  modules: { key: string; label: string }[]
  coverage_levels: { key: CoverageLevel; label: string }[]
  coverage_summary: Record<CoverageLevel, number>
  measured_from: { fixtures: number; latest_run: { id: number; reference: string; at: string } | null }
  rules: Rule[]
}
