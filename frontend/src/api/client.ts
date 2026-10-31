// Small wrapper around fetch for the DocumentLab API.
// - Sends the Django session cookie (same origin through the Vite proxy).
// - Adds the CSRF token to every request that changes data.
// - Turns error responses into an ApiError with a readable message.

export class ApiError extends Error {
  status: number
  details: unknown

  constructor(status: number, message: string, details: unknown) {
    super(message)
    this.status = status
    this.details = details
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((c) => c.startsWith(name + '='))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

async function ensureCsrfToken(): Promise<string> {
  let token = readCookie('csrftoken')
  if (!token) {
    await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
    token = readCookie('csrftoken')
  }
  if (!token) throw new ApiError(0, 'Could not get a security token from the server.', null)
  return token
}

/** Pull the most useful message out of a Django REST Framework error body. */
export function messageFrom(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const record = body as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  for (const [field, value] of Object.entries(record)) {
    const first = Array.isArray(value) ? value[0] : value
    if (typeof first === 'string') {
      return field === 'non_field_errors' ? first : `${field.replace(/_/g, ' ')}: ${first}`
    }
  }
  return fallback
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (UNSAFE.has(method)) headers['X-CSRFToken'] = await ensureCsrfToken()

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'The DocumentLab server is not reachable. Check that Django is running on port 8000.', null)
  }

  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const fallback =
      response.status === 403 ? 'You do not have permission to do that.'
      : response.status === 429 ? 'Too many attempts. Wait a minute and try again.'
      : `The server returned an error (${response.status}).`
    throw new ApiError(response.status, messageFrom(body, fallback), body)
  }
  return body as T
}
