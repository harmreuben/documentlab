import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import type { Me } from '../api/types'

const person = (role: Me['role']): Me => ({ id: 4, username: 'sam', first_name: 'Sam', last_name: '', email: '', role, role_label: role, last_login: null })

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function backend(handlers: Record<string, (init?: RequestInit) => Promise<Response>>) {
  document.cookie = 'csrftoken=test-token'
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = String(input)
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

describe('Sign-in protection', () => {
  it('returns to the sign-in page and says why after an idle sign-out', async () => {
    backend({
      '/api/auth/me/': () => json(200, person('ANALYST')),
      '/api/rules/': () => json(401, { detail: 'You were signed out after 30 minutes without activity. Sign in again to continue.', code: 'session_expired' }),
    })
    const router = open('/rules')
    expect(await screen.findByText(/signed out after 30 minutes without activity/)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('shows the account-lock message', async () => {
    backend({
      '/api/auth/me/': () => json(403, { detail: 'Not signed in.' }),
      '/api/auth/login/': () => json(429, { detail: 'Too many failed sign-ins for this account. Try again in 15 minutes, or ask an administrator to reset the password.' }),
    })
    open('/login')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'whatever-it-is')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/Too many failed sign-ins for this account/)).toBeInTheDocument()
  })
})

const ssnRoutes = {
  '/api/auth/me/': () => json(200, person('ANALYST')),
  '/api/documents/ssn-checks/': () => json(200, { count: 0, next: null, previous: null, results: [] }),
  '/api/documents/ssn-verifications/': (init?: RequestInit) => init?.method === 'POST' ? json(201, {
    id: 1, created_at: '2026-11-01T20:00:00Z', created_by: 'sam', masked: '***-**-5678', provider: 'Acme Verify', outcome: 'match',
    status: 'PASS', mismatched: [], deceased: null, provider_reference: 'T-1', consent_method: 'signed_paper', consent_reference: 'CF-1',
    consent_signed_on: '2026-10-30', purpose: 'employment', purpose_label: 'Employment or payroll',
    summary: "Acme Verify's records match the number, name and date of birth given.", ruleset_version: '2026.11.2' })
    : json(200, { count: 0, next: null, previous: null, results: [] }),
}

describe('External SSN verification', () => {
  it('explains that ownership cannot be checked without a provider', async () => {
    backend({ ...ssnRoutes, '/api/documents/ssn-verifications/meta/': () => json(200, { available: false, provider: null, purposes: [], consent_methods: [] }) })
    open('/documents?tab=ssn')
    expect(await screen.findByText(/No authorised verification provider is connected/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check with provider' })).not.toBeInTheDocument()
  })

  it('needs the full consent record, sends it, and clears the number', async () => {
    const fetchMock = backend({ ...ssnRoutes, '/api/documents/ssn-verifications/meta/': () => json(200, {
      available: true, provider: 'Acme Verify', purposes: [{ key: 'employment', label: 'Employment or payroll' }],
      consent_methods: [{ key: 'signed_paper', label: 'Signed paper form' }] }) })
    open('/documents?tab=ssn')
    const user = userEvent.setup()
    const panel = (await screen.findByRole('heading', { name: 'Check with Acme Verify' })).closest('section') ?? document.body
    const number = screen.getAllByLabelText('Social Security Number')[1]
    await user.type(number, '212-34-5678')
    await user.type(screen.getByLabelText('First name'), 'Zawadi')
    await user.type(screen.getByLabelText('Last name'), 'Example')
    await user.type(screen.getByLabelText('Date of birth'), '1980-02-03')
    await user.selectOptions(screen.getByLabelText('How it was given'), 'signed_paper')
    await user.type(screen.getByLabelText('Date signed'), '2026-10-30')
    await user.type(screen.getByLabelText('Consent form reference'), 'CF-1')
    await user.selectOptions(screen.getByLabelText('Purpose on the form'), 'employment')
    const send = screen.getByRole('button', { name: 'Check with provider' })
    expect(send).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /signed this consent/ }))
    await user.click(send)
    expect(await screen.findByText(/records match the number, name and date of birth/)).toBeInTheDocument()
    expect(number).toHaveValue('')
    const post = fetchMock.mock.calls.find(([p, i]) => String(p) === '/api/documents/ssn-verifications/' && i?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toMatchObject({ number: '212-34-5678', consent_reference: 'CF-1', consent_confirmed: true })
    expect(panel).toBeTruthy()
  })
})

describe('Security status', () => {
  const status = { status: 'FAIL', checked_at: '2026-11-01T20:00:00Z', items: [
    { key: 'debug', label: 'Debug mode', status: 'PASS', detail: 'Off.', action: '' },
    { key: 'backups', label: 'Backups', status: 'FAIL', detail: 'No backup has been made.', action: 'Run python manage.py backup_data, and schedule it daily.' },
  ] }

  it('is shown to administrators', async () => {
    backend({ '/api/auth/me/': () => json(200, person('ADMINISTRATOR')), '/api/health/': () => json(200, { status: 'ok', database: 'ok', version: '0.10.0' }),
      '/api/system/status/': () => json(200, status) })
    open('/settings')
    expect(await screen.findByText('No backup has been made.')).toBeInTheDocument()
    expect(screen.getByText(/schedule it daily/)).toBeInTheDocument()
  })

  it('is hidden from other roles', async () => {
    backend({ '/api/auth/me/': () => json(200, person('ANALYST')), '/api/health/': () => json(200, { status: 'ok', database: 'ok', version: '0.10.0' }) })
    open('/settings')
    expect(await screen.findByText('Running')).toBeInTheDocument()
    expect(screen.queryByText('Security and readiness')).not.toBeInTheDocument()
  })
})
