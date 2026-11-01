import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import type { Me } from '../api/types'
import type { TestLabMeta, TestRunDetail } from '../api/testlab'

const person = (role: Me['role']): Me => ({ id: 2, username: 'dev', first_name: 'Dee', last_name: '', email: '', role, role_label: role, last_login: null })

const meta = (over: Partial<TestLabMeta> = {}): TestLabMeta => ({
  modules: [{ key: 'analyzer', label: 'Barcode Analyzer' }, { key: 'documents', label: 'Document Analysis' }],
  tags: ['clean', 'negative'], builtin_count: 20, builtin_loaded: 20, fixtures_active: 20,
  versions: { app: '0.8.0', decoder: 'zxing-cpp 3.1.1', ocr: 'Tesseract 5.3.4' },
  can_edit_fixtures: true, can_add_document_images: false, can_run: true, ...over,
})

const empty = { count: 0, next: null, previous: null, results: [] }

const run: TestRunDetail = {
  id: 9, reference: 'RUN-20261101-ABC234', status: 'COMPLETE', scope: {}, note: 'after upgrade', total: 2, done: 2,
  passed: 1, failed: 1, errors: 0, new_failures: 1, fixed: 0, versions: { app: '0.8.0', decoder: 'zxing-cpp 3.1.1', ocr: 'Tesseract 5.3.4' },
  baseline: { id: 8, reference: 'RUN-20261031-XYZ987' }, created_by: 'dev', created_at: '2026-11-01T10:00:00Z',
  finished_at: '2026-11-01T10:00:03Z', duration_ms: 3100,
  links: { json: '/j', csv: '/c', junit: '/x' },
  cases: [
    { id: 31, fixture: 4, position: 1, fixture_name: 'Shelf label', module: 'analyzer', outcome: 'FAIL', change: 'new_failure',
      previous_outcome: 'PASS', expected: { barcode_count: 2 }, error: '', duration_ms: 120,
      actual: { status: 'PASS', summary: '1 barcode read and checked (EAN-13).', duration_ms: 120 },
      comparisons: [{ label: 'Barcodes found', expected: '2', actual: '1', passed: false }] },
    { id: 32, fixture: 5, position: 2, fixture_name: 'Passport MRZ, valid specimen', module: 'documents', outcome: 'PASS', change: 'unchanged',
      previous_outcome: 'PASS', expected: { status: ['PASS'] }, error: '', duration_ms: 2,
      actual: { status: 'PASS', summary: 'All checks passed.', duration_ms: 2 },
      comparisons: [{ label: 'Overall result', expected: 'PASS', actual: 'PASS', passed: true }] },
  ],
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function backend(me: Me, routes: Record<string, (init?: RequestInit) => Promise<Response>>) {
  document.cookie = 'csrftoken=test-token'
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = String(input)
    if (path.startsWith('/api/auth/me/')) return json(200, me)
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path.startsWith(k))
    if (key) return routes[key](init)
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

describe('Testing Laboratory', () => {
  it('offers to load the standard fixtures when there are none', async () => {
    const fetchMock = backend(person('DEVELOPER'), {
      '/api/test-lab/meta/': () => json(200, meta({ fixtures_active: 0, builtin_loaded: 0 })),
      '/api/test-lab/runs/': () => json(200, empty),
      '/api/test-lab/fixtures/load-builtin/': () => json(200, { created: 20, updated: 0 }),
    })
    open('/test-lab')
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Load the standard fixtures' }))
    expect(fetchMock.mock.calls.some(([p, i]) => String(p).includes('load-builtin') && i?.method === 'POST')).toBe(true)
  })

  it('starts a run with the chosen scope and opens it', async () => {
    const fetchMock = backend(person('ANALYST'), {
      '/api/test-lab/meta/': () => json(200, meta({ can_edit_fixtures: false })),
      '/api/test-lab/runs/9/': () => json(200, run),
      '/api/test-lab/runs/': (init) => init?.method === 'POST' ? json(201, run) : json(200, empty),
    })
    const router = open('/test-lab')
    const user = userEvent.setup()
    await user.selectOptions(await screen.findByLabelText('Module'), 'documents')
    await user.selectOptions(screen.getByLabelText('Tag'), 'negative')
    await user.click(screen.getByRole('button', { name: 'Run tests' }))
    expect(await screen.findByRole('heading', { name: "1 of 2 tests didn't behave as expected" })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/test-lab/runs/9')
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toEqual({ module: 'documents', tag: 'negative', note: '' })
  })

  it('lets read-only users see results but not start runs', async () => {
    backend(person('READ_ONLY'), {
      '/api/test-lab/meta/': () => json(200, meta({ can_run: false, can_edit_fixtures: false })),
      '/api/test-lab/runs/': () => json(200, empty),
    })
    open('/test-lab')
    expect(await screen.findByRole('button', { name: 'Run tests' })).toBeDisabled()
    expect(screen.getByText(/can view results but not start runs/)).toBeInTheDocument()
  })

  it('shows regressions and the expected-versus-actual table, and can adopt a result', async () => {
    const fetchMock = backend(person('DEVELOPER'), {
      '/api/test-lab/meta/': () => json(200, meta()),
      '/api/test-lab/runs/9/': () => json(200, run),
      '/api/test-lab/fixtures/4/adopt/': () => json(200, {}),
    })
    open('/test-lab/runs/9')
    expect(await screen.findByText(/1 test that used to pass now fails/)).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('radio', { name: 'Failed or errors' }))
    expect(screen.queryByText('Passport MRZ, valid specimen')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Shelf label/ }))
    const row = screen.getByRole('rowheader', { name: 'Barcodes found' }).closest('tr')!
    expect(row).toHaveTextContent('21Differs')
    await user.click(screen.getByRole('button', { name: 'Use this result as the expected result' }))
    expect(await screen.findByText(/Saved as this fixture's expected result/)).toBeInTheDocument()
    const adopt = fetchMock.mock.calls.find(([p]) => String(p).includes('adopt'))!
    expect(JSON.parse(adopt[1]!.body as string)).toEqual({ case_id: 31 })
  })

  it('needs the synthetic-data confirmation before saving a fixture', async () => {
    const fetchMock = backend(person('DEVELOPER'), {
      '/api/test-lab/meta/': () => json(200, meta()),
      '/api/test-lab/fixtures/': (init) => init?.method === 'POST' ? json(201, {}) : json(200, empty),
    })
    open('/test-lab?tab=fixtures')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Add a fixture' }))
    await user.type(screen.getByLabelText('Name'), 'Shelf label')
    await user.upload(screen.getByLabelText('Image or PDF'), new File([new Uint8Array([137, 80])], 'shelf.png', { type: 'image/png' }))
    const save = screen.getByRole('button', { name: 'Save fixture' })
    expect(save).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /only synthetic/ }))
    await user.click(save)
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(true))
    const form = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')![1]!.body as FormData
    expect(form.get('synthetic')).toBe('true')
    expect(JSON.parse(form.get('expected') as string)).toEqual({ status: ['PASS'] })
    expect((form.get('file') as File).name).toBe('shelf.png')
  })

  it('only offers typed MRZs for document fixtures to non-administrators', async () => {
    backend(person('DEVELOPER'), {
      '/api/test-lab/meta/': () => json(200, meta()),
      '/api/test-lab/fixtures/': () => json(200, empty),
    })
    open('/test-lab?tab=fixtures')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Add a fixture' }))
    await user.click(screen.getByRole('radio', { name: 'Document Analysis' }))
    expect(screen.getByLabelText('Machine-readable zone')).toBeInTheDocument()
    expect(screen.queryByLabelText('Image or PDF')).not.toBeInTheDocument()
    expect(screen.getByText(/Only administrators can add document images/)).toBeInTheDocument()
  })
})
