import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import { ROLE_LABELS, type ManagedUser, type Page, type Role } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Button, Loading, Notice, PageHeader, Panel } from '../components/ui'
import { cx } from '../lib/format'

const ROLES = Object.keys(ROLE_LABELS) as Role[]
const inputClass = 'mt-1 block h-9 w-full rounded-md border border-rule bg-paper px-2.5 text-sm focus:border-electric focus:outline-none'

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="text-sm">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <span id={`${id}-hint`} className="mt-1 block text-xs text-faint">{hint}</span>}
    </div>
  )
}

function NewUserForm({ onDone }: { onDone: (username: string) => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ username: '', first_name: '', last_name: '', email: '', role: 'READ_ONLY' as Role, password: '' })
  const create = useMutation({
    mutationFn: () => api<ManagedUser>('/api/auth/users/', { method: 'POST', body: form }),
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      onDone(user.username)
    },
  })
  const set = (field: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [field]: e.target.value })

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate()
  }

  return (
    <Panel title="New user" className="mb-6">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field id="new-username" label="Username"><input id="new-username" required value={form.username} onChange={set('username')} className={inputClass} autoComplete="off" /></Field>
        <Field id="new-first" label="First name"><input id="new-first" value={form.first_name} onChange={set('first_name')} className={inputClass} /></Field>
        <Field id="new-last" label="Last name"><input id="new-last" value={form.last_name} onChange={set('last_name')} className={inputClass} /></Field>
        <Field id="new-email" label="Email"><input id="new-email" type="email" value={form.email} onChange={set('email')} className={inputClass} /></Field>
        <Field id="new-role" label="Role">
          <select id="new-role" value={form.role} onChange={set('role')} className={inputClass}>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </Field>
        <Field id="new-password" label="Temporary password" hint="At least 10 characters, not only numbers.">
          <input id="new-password" required type="password" value={form.password} onChange={set('password')} className={inputClass}
            autoComplete="new-password" aria-describedby="new-password-hint" />
        </Field>
        {create.isError && (
          <div className="sm:col-span-2 lg:col-span-3">
            <Notice tone="error">{create.error instanceof ApiError ? create.error.message : 'The user was not created.'}</Notice>
          </div>
        )}
        <div className="sm:col-span-2 lg:col-span-3">
          <Button type="submit" variant="primary" disabled={create.isPending || !form.username || !form.password}>
            {create.isPending ? 'Creating…' : 'Create user'}
          </Button>
        </div>
      </form>
    </Panel>
  )
}

export function UsersPage() {
  const { user: me } = useAuth()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const users = useQuery({ queryKey: ['users'], queryFn: () => api<Page<ManagedUser>>('/api/auth/users/?page_size=100') })

  const update = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: Partial<ManagedUser> }) =>
      api<ManagedUser>(`/api/auth/users/${id}/`, { method: 'PATCH', body: changes }),
    onSuccess: (u) => {
      setMessage(`Saved changes to ${u.username}.`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  return (
    <>
      <PageHeader
        title="User management"
        description="Accounts are deactivated rather than deleted, so their history stays in the audit log."
        actions={!creating && <Button variant="primary" onClick={() => { setCreating(true); setMessage(null) }}>Add a user</Button>}
      />

      {creating && <NewUserForm onDone={(name) => { setCreating(false); setMessage(`Created ${name}.`) }} />}
      {message && <div className="mb-4"><Notice tone="success">{message}</Notice></div>}
      {update.isError && <div className="mb-4"><Notice tone="error">{update.error.message}</Notice></div>}

      <Panel title="Accounts" aside={users.data && `${users.data.count} in total`}>
        {users.isPending ? <Loading /> : users.isError ? <Notice tone="error">{users.error.message}</Notice> : (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-rule text-muted">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">User</th>
                  <th scope="col" className="px-5 py-3 font-medium">Role</th>
                  <th scope="col" className="px-5 py-3 font-medium">Last sign-in</th>
                  <th scope="col" className="px-5 py-3 font-medium">Status</th>
                  <th scope="col" className="px-5 py-3"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {users.data.results.map((u) => {
                  const self = u.id === me?.id
                  return (
                    <tr key={u.id} className={cx(!u.is_active && 'text-faint')}>
                      <td className="px-5 py-3">
                        <div className="font-medium">{u.username}{self && <span className="ml-2 text-xs font-normal text-muted">(you)</span>}</div>
                        <div className="text-xs text-muted">{[u.first_name, u.last_name].filter(Boolean).join(' ') || u.email || '—'}</div>
                      </td>
                      <td className="px-5 py-3">
                        <label className="sr-only" htmlFor={`role-${u.id}`}>Role for {u.username}</label>
                        <select id={`role-${u.id}`} value={u.role} disabled={self || update.isPending}
                          onChange={(e) => update.mutate({ id: u.id, changes: { role: e.target.value as Role } })}
                          className="h-8 rounded-md border border-rule bg-paper px-2 disabled:bg-canvas">
                          {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                        </select>
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-muted">
                        {u.last_login ? new Date(u.last_login).toLocaleString('en-GB') : 'Never'}
                      </td>
                      <td className="px-5 py-3">
                        <span className={u.is_active ? 'text-pass' : 'text-faint'}>{u.is_active ? 'Active' : 'Deactivated'}</span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        {!self && (
                          <Button variant={u.is_active ? 'danger' : 'secondary'} disabled={update.isPending}
                            onClick={() => update.mutate({ id: u.id, changes: { is_active: !u.is_active } })}>
                            {u.is_active ? 'Deactivate' : 'Reactivate'}
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="mt-3 text-xs text-faint">You can't change your own role or deactivate yourself, so the system always keeps an administrator.</p>
    </>
  )
}
