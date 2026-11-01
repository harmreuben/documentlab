import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import { ModulePage } from '../pages/ModulePage'
import { FlaskConical } from 'lucide-react'
import type { DashboardSummary, Me } from '../api/types'

const analyst: Me = {
  id: 2, username: 'ann', first_name: 'Ann', last_name: '', email: '', role: 'ANALYST',
  role_label: 'Analyst', last_login: null,
}

const summary: DashboardSummary = {
  scope: 'personal', version: '0.4.0', generated_at: '2026-10-30T12:00:00Z',
  counts: { events_24h: 3, logins_7d: 2, failed_logins_7d: null, documents_processed: null,
    barcodes_generated: 3, barcodes_failed_verification: 0, barcodes_decoded: null, pending_reviews: null },
  users: null,
  activity: Array.from({ length: 14 }, (_, i) => ({ date: `2026-10-${String(17 + i).padStart(2, '0')}`, events: i % 3 })),
  recent_activity: [{ id: 1, created_at: '2026-10-30T11:00:00Z', username: 'ann', action: 'auth.login' }],
  modules: [{ key: 'future', name: 'Future module', phase: 11, status: 'planned' }],
}

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }))
}

/** Fake backend: answers each API path the way Django would. */
function mockBackend(handlers: Record<string, () => Promise<Response>>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = String(input)
    const key = Object.keys(handlers).find((k) => path.startsWith(k))
    if (!key) throw new Error(`Unexpected request in test: ${path}`)
    return handlers[key]()
  })
}

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider><RouterProvider router={router} /></AuthProvider>
    </QueryClientProvider>,
  )
  return router
}

describe('signing in', () => {
  it('sends signed-out visitors to the login page', async () => {
    mockBackend({ '/api/auth/me/': () => json(403, { detail: 'Not signed in.' }) })
    const router = renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('shows the server message when the password is wrong', async () => {
    document.cookie = 'csrftoken=test-token'
    const fetchMock = mockBackend({
      '/api/auth/me/': () => json(403, { detail: 'Not signed in.' }),
      '/api/auth/login/': () => json(401, { detail: 'Invalid username or password.' }),
    })
    renderAt('/login')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Username'), 'ann')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.')
    // The CSRF token was sent with the login request.
    const loginCall = fetchMock.mock.calls.find(([url]) => String(url).startsWith('/api/auth/login/'))!
    expect((loginCall[1]!.headers as Record<string, string>)['X-CSRFToken']).toBe('test-token')
  })

  it('opens the dashboard after a successful sign-in', async () => {
    document.cookie = 'csrftoken=test-token'
    mockBackend({
      '/api/auth/me/': () => json(403, { detail: 'Not signed in.' }),
      '/api/auth/login/': () => json(200, analyst),
      '/api/dashboard/summary/': () => json(200, summary),
    })
    const router = renderAt('/login')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Username'), 'ann')
    await user.type(screen.getByLabelText('Password'), 'Correct-Passw0rd')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Welcome back, Ann' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByText('Arrives with the Barcode Analyzer')).toBeInTheDocument()
  })
})

describe('signed-in pages', () => {
  it('blocks the audit log for non-administrators', async () => {
    mockBackend({ '/api/auth/me/': () => json(200, analyst) })
    renderAt('/audit')
    expect(await screen.findByRole('heading', { name: "You don't have access to this page" })).toBeInTheDocument()
  })

  it('says plainly that an unbuilt workspace does not work yet', async () => {
    mockBackend({ '/api/dashboard/summary/': () => json(200, summary) })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ModulePage item={{ key: 'future', label: 'Future module', path: '/future', icon: FlaskConical, description: 'Not yet.' }} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('This workspace is not built yet.')).toBeInTheDocument()
    expect(await screen.findByText(/It arrives in Phase 11/)).toBeInTheDocument()
  })
})
