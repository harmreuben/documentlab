// Types for /api/reviews/ and the review block on analysis records.
import type { ResultStatus } from './analyzer'

export type ReviewState = '' | 'PENDING' | 'CONFIRMED' | 'REJECTED' | 'EXPIRED'

export interface ReviewInfo {
  review_state: ReviewState
  review_label: string
  reviewed_by: string | null
  reviewed_at: string | null
  review_note: string
  can_review?: boolean
  own?: boolean
}

export interface QueueItem extends ReviewInfo {
  kind: 'barcode' | 'document'
  id: number
  reference: string
  label: string
  created_at: string
  created_by: string | null
  status: ResultStatus
  summary: string
  path: string
}

export interface Queue {
  pending: number
  results: QueueItem[]
}
