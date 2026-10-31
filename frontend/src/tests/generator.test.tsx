import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '../auth/AuthContext'
import { routes } from '../routes'
import type { Me } from '../api/types'
import type { CheckResponse, FormatsResponse, GeneratedBarcode } from '../api/generator'

const analyst: Me = { id: 2, username: 'ann', first_name: 'Ann', last_name: '', email: '', role: 'ANALYST', role_label: 'Analyst', last_login: null }
const readOnly: Me = { ...analyst, id: 3, username: 'rob', role: 'READ_ONLY', role_label: 'Read-only user' }

const colour = [
  { name: 'foreground', label: 'Bar colour', kind: 'colour', default: '#000000' },
  { name: 'background', label: 'Background', kind: 'colour', default: '#FFFFFF' },
] as const

const formats: FormatsResponse = {
  default_schema: 'documentlab.text.v1',
  schemas: [{ id: 'documentlab.text.v1', name: 'Plain text', description: 'Encodes exactly the text you enter.', structured: false, fields: [] }],
  formats: [
    { key: 'qr', name: 'QR Code', family: 'matrix', summary: 'Square 2D code.', max_length: 1000, structured: true, digits: null, notes: [],
      options: [{ name: 'module_size', label: 'Module size', kind: 'integer', default: 8, minimum: 1, maximum: 40, unit: 'px' }, ...colour] },
    { key: 'ean13', name: 'EAN-13', family: 'linear', summary: '13-digit retail number.', max_length: 13, structured: false, digits: [12, 13], notes: [],
      options: [{ name: 'show_text', label: 'Print the text under the bars', kind: 'boolean', default: true }, ...colour] },
  ],
}

const okCheck: CheckResponse = {
  ok: true, format: 'ean13', schema: 'documentlab.text.v1', expected_decode: '5901234123457', check_digit: '7',
  options: {}, errors: [], warnings: [], blocked: false,
  preview: { svg_data_url: 'data:image/svg+xml;base64,PHN2Zy8+', width: 100, height: 50, details: {} },
  verification: { status: 'PASS', decoded_text: '5901234123457', decoded_format: 'EAN-13', detail: 'Decoded by an independent reader and matched exactly.' },
}

const badCheck: CheckResponse = {
  ...okCheck, ok: false, expected_decode: '', check_digit: null, preview: null, verification: null,
  errors: [{ field: 'payload', message: 'The check digit should be 7, not 8.' }],
}

const saved = {
  id: 1, test_reference: 'GEN-20261031-ABC234', verification_status: 'PASS', verification_detail: 'ok',
  downloads: { png: '/png', svg: '/svg', pdf: '/pdf' },
} as unknown as GeneratedBarcode

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function backend(user: Me, check: (body: { payload: string }) => CheckResponse) {
  document.cookie = 'csrftoken=test-token'
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = String(input)
    if (path.startsWith('/api/auth/me/')) return json(200, user)
    if (path.startsWith('/api/generator/formats/')) return json(200, formats)
    if (path.startsWith('/api/generator/check/')) return json(200, check(JSON.parse(String(init?.body))))
    if (path.startsWith('/api/generator/barcodes/') && init?.method === 'POST') return json(201, saved)
    throw new Error(`Unexpected request in test: ${path}`)
  })
}

function open() {
  const router = createMemoryRouter(routes, { initialEntries: ['/generator'] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthProvider><RouterProvider router={router} /></AuthProvider>
    </QueryClientProvider>,
  )
}

describe('Barcode Generator', () => {
  it('previews, shows the decoder verdict, then saves', async () => {
    const fetchMock = backend(analyst, () => okCheck)
    open()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('radio', { name: /EAN-13/ }))
    const generateButton = screen.getByRole('button', { name: 'Generate and verify' })
    expect(generateButton).toBeDisabled()

    await user.type(screen.getByLabelText('Data to encode'), '590123412345')
    expect(await screen.findByRole('img', { name: 'EAN-13 preview' })).toBeInTheDocument()
    expect(screen.getByText('5901234123457')).toBeInTheDocument()
    expect(screen.getByText('Pass')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Generate and verify' }))
    const result = await screen.findByRole('heading', { name: 'Saved and verified' })
    expect(within(result.closest('section')!).getByText('GEN-20261031-ABC234')).toBeInTheDocument()

    const post = fetchMock.mock.calls.find(([url, init]) => String(url).startsWith('/api/generator/barcodes/') && init?.method === 'POST')!
    expect(JSON.parse(String(post[1]!.body))).toMatchObject({ format: 'ean13', payload: '590123412345' })
  })

  it('shows the server explanation under the field and blocks saving', async () => {
    backend(analyst, () => badCheck)
    open()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('radio', { name: /EAN-13/ }))
    await user.type(screen.getByLabelText('Data to encode'), '5901234123458')
    expect(await screen.findByText('The check digit should be 7, not 8.')).toBeInTheDocument()
    expect(screen.getByLabelText('Data to encode')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('button', { name: 'Generate and verify' })).toBeDisabled()
  })

  it('lets read-only users preview but not save', async () => {
    backend(readOnly, () => okCheck)
    open()
    expect(await screen.findByText(/read-only, so you can preview/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate and verify' })).not.toBeInTheDocument()
  })
})
