import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { Logo } from '../components/Logo'
import { Button, Notice } from '../components/ui'
import { ALL_NAV_ITEMS } from '../navigation'
import type { Me } from '../api/types'

/** Return to the page that was asked for, unless this user's role can't open it. */
function allowedDestination(path: string, user: Me): string {
  const item = ALL_NAV_ITEMS.find((i) => i.path === path)
  return item?.roles && !item.roles.includes(user.role) ? '/' : path
}

const VERBS = ['Analyse.', 'Generate.', 'Validate.', 'Test.', 'Report.']

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const destination = (location.state as { from?: string } | null)?.from ?? '/'
  if (user) return <Navigate to={allowedDestination(destination, user)} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const signedIn = await login(username.trim(), password)
      navigate(allowedDestination(destination, signedIn), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed. Try again.')
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="flex flex-col justify-between bg-ink px-8 py-10 text-white sm:px-12 lg:py-14">
        <Logo />
        <p aria-label="Analyse, generate, validate, test, report" className="my-12 text-[2.6rem] leading-[1.08] font-semibold tracking-[-0.02em] sm:text-[3.2rem]">
          {VERBS.map((verb, i) => (
            <span key={verb} className={i === 2 ? 'block text-white' : 'block text-[#56637A]'}>{verb}</span>
          ))}
        </p>
        <p className="max-w-sm text-sm leading-relaxed text-faint">
          Technical checks only. A barcode that decodes, or fields that agree, are not proof that a document is genuine.
        </p>
      </div>

      <div className="flex items-center justify-center bg-paper px-6 py-12">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5" noValidate>
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.01em]">Sign in</h1>
            <p className="mt-1.5 text-sm text-muted">Use the account your administrator created for you.</p>
          </div>

          {error && <Notice tone="error">{error}</Notice>}

          <label className="block">
            <span className="text-sm font-medium">Username</span>
            <input
              name="username" autoComplete="username" required autoFocus
              value={username} onChange={(e) => setUsername(e.target.value)}
              className="mt-1.5 block h-10 w-full rounded-md border border-rule px-3 text-[0.95rem] focus:border-electric focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium">Password</span>
            <input
              name="password" type="password" autoComplete="current-password" required
              value={password} onChange={(e) => setPassword(e.target.value)}
              className="mt-1.5 block h-10 w-full rounded-md border border-rule px-3 text-[0.95rem] focus:border-electric focus:outline-none"
            />
          </label>

          <Button type="submit" variant="primary" className="h-10 w-full" disabled={busy || !username || !password}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </div>
    </div>
  )
}
