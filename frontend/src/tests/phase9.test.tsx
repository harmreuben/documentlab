import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import type { Me } from '../api/types'
import type { DocumentAnalysis } from '../api/documents'
import type { RulesResponse } from '../api/rules'

const person = (role: Me['role'], username = 'rita'): Me => ({ id: 3, username, first_name: 'Rita', last_name: '', email: '', role, role_label: role, last_login: null })

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function backend(me: Me, handlers: Record<string, (init?: RequestInit) => Promise<Response>>) {
  document.cookie = 'csrftoken=test-token'
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = String(input)
    if (path.startsWith('/api/auth/me/')) return json(200, me)
    const key = Object.keys(handlers).sort((a, b) => b.length - a.length).find((k) => path.startsWith(k))
    if (key) return handlers[key](init)
    throw new Error(`Unexpected request in test: ${init?.method ?? 'GET'} ${path}`)
  })
}

function open(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthProvider><RouterProvider router={router} /></AuthProvider>
    </QueryClientProvider>,
  )
  return router
}

afterEach(() => vi.restoreAllMocks())

const rules: RulesResponse = {
  ruleset_version: '2026.11.1',
  modules: [{ key: 'documents', label: 'Document Analysis' }, { key: 'ssn', label: 'SSN format check' }],
  coverage_levels: [{ key: 'full', label: 'Fully tested' }, { key: 'partial', label: 'Partly tested' },
    { key: 'none', label: 'Not tested' }, { key: 'outside', label: 'Outside the Testing Laboratory' }],
  coverage_summary: { full: 1, partial: 0, none: 0, outside: 1 },
  measured_from: { fixtures: 20, latest_run: { id: 4, reference: 'RUN-20261101-AAAAAA', at: '2026-11-01T10:00:00Z' } },
  rules: [
    { code: 'mrz.check_digit.*', name: 'Check digits', module: 'documents', module_label: 'Document Analysis', category: 'data_format',
      checks: 'Recalculates each check digit with weights 7, 3, 1.', outcomes: { PASS: 'The digit matches.', FAIL: "The digit doesn't match." },
      reference: 'ICAO Doc 9303', version: 1, since: '0.7.0', changes: [], parameters: {}, keys: ['mrz.check_digit.composite'],
      severity: 'blocking', severity_label: 'Can fail the result',
      coverage: { level: 'full', label: 'Fully tested', statuses: ['FAIL', 'PASS'],
        exercised_by: [{ id: 1, name: 'Passport MRZ, wrong check digit', statuses: ['FAIL', 'PASS'] }], asserted_by: [{ id: 1, name: 'Passport MRZ, wrong check digit' }] } },
    { code: 'ssn.area', name: 'Area number', module: 'ssn', module_label: 'SSN format check', category: 'data_format',
      checks: 'The first three digits cannot be 000, 666 or 900-999.', outcomes: { PASS: 'Allowed.', FAIL: 'Never issued.' },
      reference: 'SSA', version: 1, since: '0.7.0', changes: [], parameters: {}, keys: ['ssn.area'], severity: 'blocking',
      severity_label: 'Can fail the result', coverage: { level: 'outside', label: 'Outside the Testing Laboratory', statuses: [], exercised_by: [], asserted_by: [] } },
  ],
}

describe('Validation Rules', () => {
  it('shows measured coverage, filters by it and explains a rule', async () => {
    backend(person('READ_ONLY'), { '/api/rules/': () => json(200, rules) })
    open('/rules')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Outside the Testing Laboratory/, pressed: false }))
    expect(screen.queryByRole('button', { name: /Check digits/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Outside the Testing Laboratory/, pressed: true }))
    await user.click(screen.getByRole('button', { name: /Check digits/ }))
    expect(screen.getByText("The digit doesn't match.")).toBeInTheDocument()
    expect(screen.getByText(/Seen as Fail, Pass across 1 fixture/)).toBeInTheDocument()
    expect(screen.getByText('asserted')).toBeInTheDocument()
  })
})

const doc = (over: Partial<DocumentAnalysis> = {}): DocumentAnalysis => ({
  id: 7, reference: 'DOC-20261101-REVIEW', created_at: '2026-11-01T10:00:00Z', created_by: 'ann', source: 'manual_mrz',
  requested_type: 'id_card', detected_type: 'passport', document_label: 'Passport', status: 'REVIEW_REQUIRED',
  summary: 'Needs review: You chose ID card, but the data looks like a passport.', next_action: 'Have a reviewer look at the highlighted checks.',
  checks: [], fields: {}, mrz: null, licence: null, ocr: [], pages: [], warnings: [], ocr_engine: '', duration_ms: 2,
  authenticity: { status: 'NOT_CHECKED', detail: 'Technical checks only.' }, upload: null, expires_at: '2026-12-01T10:00:00Z',
  purged_at: null, purge_reason: '', ruleset_version: '2026.11.1', links: { pages: [], pdf: '/api/documents/analyses/7/report/' },
  review: { review_state: 'PENDING', review_label: 'Waiting for review', reviewed_by: null, reviewed_at: null, review_note: '' },
  ...over,
})

describe('Reviews', () => {
  it('lets another reviewer confirm, and requires a note to reject', async () => {
    const fetchMock = backend(person('REVIEWER'), {
      '/api/documents/analyses/7/': () => json(200, doc()),
      '/api/reviews/document/7/': () => json(200, { review_state: 'CONFIRMED', review_label: 'Confirmed', reviewed_by: 'rita',
        reviewed_at: '2026-11-01T11:00:00Z', review_note: 'Checked the card.' }),
    })
    open('/documents/7')
    const user = userEvent.setup()
    expect(await screen.findByRole('button', { name: 'Reject' })).toBeDisabled()
    await user.type(screen.getByLabelText('Note'), 'Checked the card.')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByText('Confirmed')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toEqual({ decision: 'CONFIRMED', note: 'Checked the card.' })
    expect(screen.getByRole('link', { name: 'PDF report' })).toHaveAttribute('href', '/api/documents/analyses/7/report/')
  })

  it('never offers review on your own analysis', async () => {
    backend(person('REVIEWER', 'ann'), { '/api/documents/analyses/7/': () => json(200, doc()) })
    open('/documents/7')
    expect(await screen.findByText(/nobody reviews their own analysis/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })

  it('lists waiting items with a link to review them', async () => {
    backend(person('REVIEWER'), {
      '/api/reviews/': () => json(200, { pending: 1, results: [{ kind: 'document', id: 7, reference: 'DOC-20261101-REVIEW', label: 'Document Analysis',
        created_at: '2026-11-01T10:00:00Z', created_by: 'ann', status: 'REVIEW_REQUIRED', summary: 'Needs review: type differs.', path: '/documents/7',
        review_state: 'PENDING', review_label: 'Waiting for review', reviewed_by: null, reviewed_at: null, review_note: '', can_review: true, own: false }] }),
    })
    open('/reviews')
    expect(await screen.findByRole('tab', { name: 'Waiting (1)' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review' })).toHaveAttribute('href', '/documents/7')
  })
})

describe('Reports', () => {
  it('shows the summary for the chosen period with download links', async () => {
    backend(person('ANALYST'), {
      '/api/reports/summary/': () => json(200, {
        start: '2026-10-03', end: '2026-11-01', scope: 'own', ruleset_version: '2026.11.1', app_version: '0.9.0',
        sections: { analyzer: { label: 'Barcode Analyzer', total: 4, by_status: { PASS: 3, FAIL: 1 }, reviews: {} },
          documents: { label: 'Document Analysis', total: 2, by_status: { PASS: 1, REVIEW_REQUIRED: 1 }, reviews: { PENDING: 1 } },
          test_lab: { label: 'Testing Laboratory', runs: 1, runs_with_failures: 0, last_run: { reference: 'RUN-1', passed: 20, total: 20 } } },
        rules: [{ code: 'document.type', name: 'Document type matches', module: 'documents', failed: 0, review: 1 }] }),
    })
    open('/reports')
    expect(await screen.findByText('Pass 3 · Fail 1')).toBeInTheDocument()
    expect(screen.getByText('Waiting 1')).toBeInTheDocument()
    expect(screen.getByText('1 needed review')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download PDF' }).getAttribute('href')).toMatch(/^\/api\/reports\/summary\/\?start=\d{4}-\d{2}-\d{2}&end=\d{4}-\d{2}-\d{2}&type=pdf$/)
    expect(screen.getByText('your own work', { exact: false })).toBeInTheDocument()
  })
})
