import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ReviewInfo } from '../api/reviews'
import { useAuth } from '../auth/AuthContext'
import { formatDateTime } from '../lib/format'
import { Button, Notice, Panel } from './ui'

const REVIEWERS = ['ADMINISTRATOR', 'REVIEWER']

/**
 * A second person's decision on a result that needs review. Shown only when a review applies.
 * The decision sits beside the technical result; it never replaces it.
 */
export function ReviewPanel({ kind, id, createdBy, review, purged = false, queryKey }: {
  kind: 'barcode' | 'document'; id: number; createdBy: string | null; review: ReviewInfo; purged?: boolean
  queryKey: unknown[]
}) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const decide = useMutation({
    mutationFn: (decision: 'CONFIRMED' | 'REJECTED') =>
      api<ReviewInfo>(`/api/reviews/${kind}/${id}/`, { method: 'POST', body: { decision, note } }),
    onSuccess: (info) => {
      queryClient.setQueryData(queryKey, (old: { review: ReviewInfo } | undefined) => old && { ...old, review: { ...old.review, ...info } })
      queryClient.invalidateQueries({ queryKey: ['reviews'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (!review.review_state) return null
  const own = !!user && user.username === createdBy
  const canDecide = review.review_state === 'PENDING' && !!user && REVIEWERS.includes(user.role) && !own && !purged

  return (
    <Panel title="Review">
      {review.review_state === 'PENDING' ? (
        <p className="text-sm">
          <span className="font-medium">Waiting for review.</span>{' '}
          <span className="text-muted">
            {canDecide ? 'Compare the flagged checks with the original, then confirm or reject.'
              : own ? 'Another reviewer must check this, because nobody reviews their own analysis.'
              : 'A reviewer or administrator will check the flagged items.'}
          </span>
        </p>
      ) : review.review_state === 'EXPIRED' ? (
        <p className="text-sm text-muted">The data was deleted before anyone reviewed it.</p>
      ) : (
        <div className="text-sm">
          <p><span className={review.review_state === 'CONFIRMED' ? 'font-medium text-pass' : 'font-medium text-fail'}>{review.review_label}</span>
            {review.reviewed_by && <span className="text-muted"> by {review.reviewed_by}</span>}
            {review.reviewed_at && <span className="text-muted">, {formatDateTime(review.reviewed_at)}</span>}</p>
          {review.review_note && <p className="mt-2 rounded-md bg-canvas px-3 py-2">{review.review_note}</p>}
        </div>
      )}
      {canDecide && (
        <div className="mt-4 space-y-3 border-t border-rule pt-4">
          <div>
            <label htmlFor="review-note" className="mb-1 block text-sm font-medium">Note</label>
            <textarea id="review-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500}
              aria-describedby="review-note-hint"
              className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:border-electric focus:outline-none" />
            <p id="review-note-hint" className="mt-1 text-xs text-faint">Required when rejecting. Don't copy personal details into the note.</p>
          </div>
          {decide.isError && <Notice tone="error">{decide.error.message}</Notice>}
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" disabled={decide.isPending} onClick={() => decide.mutate('CONFIRMED')}>Confirm</Button>
            <Button variant="danger" disabled={decide.isPending || !note.trim()} onClick={() => decide.mutate('REJECTED')}>Reject</Button>
          </div>
          <p className="text-xs text-faint">Confirming means the flagged items match the original. It doesn't make the result a pass, and it doesn't show the document is genuine.</p>
        </div>
      )}
    </Panel>
  )
}
