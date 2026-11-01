import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import type { Me } from '../api/types'
import type { Analysis, DecodedBarcode } from '../api/analyzer'

const analyst: Me = { id: 2, username: 'ann', first_name: 'Ann', last_name: '', email: '', role: 'ANALYST', role_label: 'Analyst', last_login: null }

const ean: DecodedBarcode = {
  id: 11, page: 1, index: 1, format_name: 'EAN-13', format_key: 'ean13', supported: true, text: '5901234123457',
  byte_length: 13, valid: true, error: '', points: [[10, 10], [200, 10], [200, 100], [10, 100]], tilt: 0, ec_level: '',
  symbology_identifier: ']E0', consistent_reads: 3, attempts: 3, alternatives: {},
  interpretation: { kind: 'gs1_retail', summary: 'Retail product number', data_check: 'PASS', data_detail: 'The check digit is correct.',
    fields: [{ label: 'Check digit', value: '7' }], notes: [], sensitive: false },
  findings: [], expected_match: true, status: 'PASS', reason: 'Decoded, valid and read consistently.', matched_generated: null,
}

const base: Analysis = {
  id: 5, reference: 'ANA-20261101-ABC234', created_at: '2026-11-01T10:00:00Z', created_by: 'ann',
  upload: { original_name: 'shelf.png', kind: 'png', size_bytes: 20480, sha256: 'a'.repeat(64), page_count: 1, file_available: true, file_removed_reason: '' },
  source_generated: null, expected_value: '5901234123457', status: 'PASS', summary: '1 barcode read and checked (EAN-13).',
  next_action: 'No action needed.',
  checks: [
    { category: 'file_integrity', status: 'PASS', detail: 'PNG file opened; 1 page(s) analysed.' },
    { category: 'image_quality', status: 'PASS', detail: 'No image-quality problems found.' },
    { category: 'barcode_decoding', status: 'PASS', detail: '1 of 1 barcode(s) decoded.' },
    { category: 'data_format', status: 'PASS', detail: 'The check digit is correct.' },
    { category: 'expected_value', status: 'PASS', detail: 'A barcode matches the expected value.' },
  ],
  pages: [{ page: 1, width: 523, height: 274, sharpness: 11000, contrast_range: 1, mean_brightness: 0.8, findings: [] }],
  warnings: [], sensitive: false, duration_ms: 24, decoder: 'zxing-cpp 3.1.1', barcodes: [ean],
  links: { json: '/json', csv: '/csv', pdf: '/pdf', pages: ['/api/analyzer/analyses/5/image/?page=1'] },
  review: { review_state: '', review_label: 'Not needed', reviewed_by: null, reviewed_at: null, review_note: '' }, ruleset_version: '2026.11.1',
}

const withheld: Analysis = {
  ...base, id: 6, status: 'REVIEW_REQUIRED', sensitive: true, expected_value: '',
  summary: "This barcode holds data laid out like a driver's licence, ID card or passport.",
  next_action: 'Identity documents are handled in Document Analysis (Phase 7).',
  upload: { ...base.upload, file_available: false, file_removed_reason: 'Removed: the file contained identity-document data.' },
  links: { json: '/json', csv: '/csv', pdf: '/pdf' },
  barcodes: [{ ...ean, format_name: 'PDF417', text: null, status: 'REVIEW_REQUIRED', expected_match: null,
    interpretation: { ...ean.interpretation, kind: 'identity_document', summary: 'Identity document data', data_check: 'REVIEW_REQUIRED',
      data_detail: 'It is not displayed or stored by the Barcode Analyzer.', fields: [], sensitive: true } }],
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function backend(extra: Record<string, () => Promise<Response>> = {}) {
  document.cookie = 'csrftoken=test-token'
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = String(input)
    if (path.startsWith('/api/auth/me/')) return json(200, analyst)
    for (const [prefix, handler] of Object.entries(extra)) {
      if (path.startsWith(prefix) && (!prefix.endsWith('POST') || init?.method === 'POST')) return handler()
    }
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

describe('Barcode Analyzer', () => {
  it('uploads the chosen file with the expected value, then opens the result', async () => {
    const fetchMock = backend({
      '/api/analyzer/analyses/5/': () => json(200, base),
      '/api/analyzer/analyses/': () => json(201, base),
    })
    const router = open('/analyzer')
    const user = userEvent.setup()
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'shelf.png', { type: 'image/png' })
    await user.upload(await screen.findByLabelText(/Drop a file here/), file)
    await user.type(screen.getByLabelText('Expected value (optional)'), '5901234123457')
    await user.click(screen.getByRole('button', { name: 'Analyse file' }))

    expect(await screen.findByRole('heading', { name: '1 barcode read and checked (EAN-13).' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/analyzer/5')
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    const form = post[1]!.body as FormData
    expect((form.get('file') as File).name).toBe('shelf.png')
    expect(form.get('expected')).toBe('5901234123457')
  })

  it('shows checks, the outlined page image and each barcode', async () => {
    backend({ '/api/analyzer/analyses/5/': () => json(200, base) })
    open('/analyzer/5')
    expect(await screen.findByRole('img', { name: 'Page 1 of shelf.png' })).toHaveAttribute('src', '/api/analyzer/analyses/5/image/?page=1')
    expect(screen.getByText('Expected value')).toBeInTheDocument()
    const card = screen.getByRole('button', { name: /EAN-13/ }).closest('li')!
    expect(within(card).getByText('5901234123457')).toBeInTheDocument()
    expect(within(card).getByText('Matches the expected value.')).toBeInTheDocument()
    expect(within(card).getByText('3 of 3')).toBeInTheDocument()
  })

  it('never shows withheld identity data or its image', async () => {
    backend({ '/api/analyzer/analyses/6/': () => json(200, withheld) })
    open('/analyzer/6')
    expect(await screen.findByText(/Withheld\./)).toBeInTheDocument()
    expect(screen.getByText('Removed: the file contained identity-document data.')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Page 1/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('Needs review').length).toBeGreaterThan(0)
  })
})
