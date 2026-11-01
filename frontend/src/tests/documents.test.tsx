import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import type { Me } from '../api/types'
import type { DocumentAnalysis, SsnResult } from '../api/documents'

// Synthetic data only: ICAO 9303's fictional specimen holder.
const L1 = 'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<'
const L2 = 'L898902C36UTO7408122F3104150ZE184226B<<<<<16'

const person = (role: Me['role']): Me => ({ id: 2, username: 'ann', first_name: 'Ann', last_name: '', email: '', role, role_label: role, last_login: null })

const meta = { types: [{ key: 'auto', label: 'Detect automatically' }, { key: 'passport', label: 'Passport' }], retention_days: 30, ocr: { available: true, engine: 'Tesseract 5.3' } }

const passport: DocumentAnalysis = {
  id: 7, reference: 'DOC-20261101-XYZ234', created_at: '2026-11-01T10:00:00Z', created_by: 'ann', source: 'manual_mrz',
  requested_type: 'auto', detected_type: 'passport', document_label: 'Passport', status: 'PASS',
  summary: 'The machine-readable zone is complete and every check digit is correct.', next_action: 'No action needed.',
  checks: [
    { category: 'data_format', code: 'mrz.check_digit.document_number', name: 'Document number check digit', status: 'PASS', detail: 'Expected 6, found 6.' },
    { category: 'dates', code: 'mrz.not_expired', name: 'Not expired', status: 'PASS', detail: 'Expires on 15 April 2031.' },
    { category: 'external', code: 'external.verification', name: 'Issuer verification', status: 'UNAVAILABLE', detail: 'Needs an authorised provider.' },
  ],
  fields: {
    surname: { label: 'Surname', value: 'ERIKSSON', display: 'ERIKSSON', source: 'MRZ' },
    document_number: { label: 'Document number', value: 'L898902C3', display: 'L898902C3', source: 'MRZ' },
  },
  mrz: {
    layout: 'TD3', lines: [L1, L2], original: [L1, L2], fields: {}, status: 'PASS', corrections: [],
    checks: [{ category: 'data_format', code: 'mrz.check_digit.document_number', name: 'Document number', status: 'PASS', positions: [[2, 1], [2, 10]] }],
    segments: [
      { line: 1, start: 0, end: 44, field: 'name' },
      { line: 2, start: 0, end: 9, field: 'document_number' }, { line: 2, start: 9, end: 10, field: 'check' },
      { line: 2, start: 10, end: 44, field: 'optional_data' },
    ],
  },
  licence: null, ocr: [], pages: [], warnings: [], ocr_engine: '', duration_ms: 3,
  authenticity: { status: 'NOT_CHECKED', detail: "These checks can't show that the document is genuine." },
  upload: null, expires_at: '2026-12-01T10:00:00Z', purged_at: null, purge_reason: '', links: { pages: [] },
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function backend(me: Me, extra: Record<string, (init?: RequestInit) => Promise<Response>> = {}) {
  document.cookie = 'csrftoken=test-token'
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = String(input)
    if (path.startsWith('/api/auth/me/')) return json(200, me)
    if (path.startsWith('/api/documents/meta/')) return json(200, meta)
    for (const [prefix, handler] of Object.entries(extra)) if (path.startsWith(prefix)) return handler(init)
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

describe('Document Analysis', () => {
  it('needs the authorisation box ticked, then sends the typed MRZ and opens the result', async () => {
    const fetchMock = backend(person('ANALYST'), {
      '/api/documents/analyses/7/': () => json(200, passport),
      '/api/documents/analyses/': () => json(201, passport),
    })
    const router = open('/documents')
    const user = userEvent.setup()
    await user.click(await screen.findByText('Type the MRZ'))
    await user.type(screen.getByLabelText('Machine-readable zone'), `${L1}\n${L2}`)
    const button = screen.getByRole('button', { name: 'Analyse document' })
    expect(button).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /authorised to process/ }))
    await user.click(button)

    expect(await screen.findByRole('heading', { name: passport.summary })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/documents/7')
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toMatchObject({ authorised: true, document_type: 'auto' })
  })

  it('always says authenticity was not checked, and shows the MRZ check digit', async () => {
    backend(person('ANALYST'), { '/api/documents/analyses/7/': () => json(200, passport) })
    open('/documents/7')
    expect(await screen.findByText('Authenticity not checked.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Machine-readable zone, TD3, 2 lines/ })).toBeInTheDocument()
    expect(screen.getByText('Issuer verification')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Delete personal data now' })).toBeInTheDocument()
  })

  it('shows only the remaining outline once personal data is deleted', async () => {
    const purged = { ...passport, fields: {}, mrz: null, purged_at: '2026-11-02T10:00:00Z', purge_reason: 'deleted by the user' }
    backend(person('ANALYST'), { '/api/documents/analyses/7/': () => json(200, purged) })
    open('/documents/7')
    expect(await screen.findByText(/Personal data was deleted on 2 November 2026/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete personal data now' })).not.toBeInTheDocument()
  })

  it('clears the SSN from the screen and shows only the masked result', async () => {
    const result: SsnResult = { id: 1, masked: '***-**-1234', format_valid: true, status: 'PASS', created_at: '2026-11-01T10:00:00Z',
      checks: [{ category: 'data_format', code: 'ssn.area', name: 'Area number', status: 'PASS', detail: 'Allowed.' }],
      statement: "A valid format doesn't show that the number was issued or who it belongs to." }
    backend(person('REVIEWER'), {
      '/api/documents/ssn-checks/': (init) => init?.method === 'POST' ? json(201, result) : json(200, { count: 0, next: null, previous: null, results: [] }),
    })
    open('/documents?tab=ssn')
    const user = userEvent.setup()
    const input = await screen.findByLabelText('Social Security Number')
    await user.type(input, '212-34-1234')
    await user.click(screen.getByRole('button', { name: 'Check format' }))
    expect(await screen.findByText('Result for ***-**-1234')).toBeInTheDocument()
    expect(input).toHaveValue('')
    expect(screen.queryByText(/212-34-1234/)).not.toBeInTheDocument()
    expect(screen.getByText(/doesn't show that the number was issued/)).toBeInTheDocument()
  })

  it('compares chosen records field by field', async () => {
    const item = (id: number) => ({ id, reference: `DOC-${id}`, created_at: '', created_by: 'ann', source: 'upload', detected_type: 'passport',
      document_label: 'Passport', status: 'PASS', holder: 'E.', number: '•••2C3', expires_at: '2026-12-01T00:00:00Z', purged_at: null })
    const comparison = { id: 1, reference: 'CMP-1', created_at: '', status: 'FAIL', summary: '1 field differs.', expires_at: '', purged_at: null,
      documents: [{ id: 1, reference: 'DOC-1', document_label: 'Passport' }, { id: 2, reference: 'DOC-2', document_label: 'Passport' }],
      rows: [{ field: 'birth_date', label: 'Date of birth', status: 'FAIL', reason: 'Different values.', action: 'Check both documents.',
        values: [{ reference: 'DOC-1', document_type: 'passport', value: '12 August 1974' }, { reference: 'DOC-2', document_type: 'passport', value: '21 August 1974' }] }] }
    const fetchMock = backend(person('ANALYST'), {
      '/api/documents/analyses/': () => json(200, { count: 2, next: null, previous: null, results: [item(1), item(2)] }),
      '/api/documents/comparisons/': () => json(201, comparison),
    })
    open('/documents?tab=compare')
    const user = userEvent.setup()
    const boxes = await screen.findAllByRole('checkbox')
    await user.click(boxes[0]); await user.click(boxes[1])
    await user.click(screen.getByRole('button', { name: 'Compare documents' }))
    const row = (await screen.findByRole('rowheader', { name: 'Date of birth' })).closest('tr')!
    expect(within(row).getByText('21 August 1974')).toBeInTheDocument()
    expect(within(row).getByText('Different values.')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toEqual({ analysis_ids: [1, 2] })
  })

  it('keeps developers and read-only users out', async () => {
    backend(person('DEVELOPER'))
    open('/documents')
    expect(await screen.findByText(/don't have access|not available to your role/i)).toBeInTheDocument()
  })
})
