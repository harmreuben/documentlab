import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'
import { LogOut, Menu, X } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { visibleNavigation } from '../navigation'
import { Logo } from './Logo'
import { cx } from '../lib/format'

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth()
  return (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-5">
      {visibleNavigation(user?.role).map((group) => (
        <div key={group.label}>
          <div className="px-3 pb-1.5 text-xs font-medium text-faint">{group.label}</div>
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.key}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  onClick={onNavigate}
                  className={({ isActive }) => cx(
                    'relative flex items-center gap-3 rounded-md px-3 py-2 text-sm',
                    isActive
                      ? 'bg-ink-soft font-medium text-white before:absolute before:top-1.5 before:bottom-1.5 before:left-0 before:w-[3px] before:rounded-full before:bg-electric'
                      : 'text-[#B8C1D1] hover:bg-ink-soft hover:text-white',
                  )}
                >
                  <item.icon size={17} strokeWidth={1.75} aria-hidden="true" />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  async function signOut() {
    await logout()
    navigate('/login', { replace: true })
  }

  const account = user && (
    <div className="border-t border-ink-line px-5 py-4">
      <div className="truncate text-sm font-medium text-white">{user.username}</div>
      <div className="text-xs text-faint">{user.role_label}</div>
      <button
        type="button"
        onClick={signOut}
        className="mt-3 inline-flex items-center gap-2 text-sm text-[#B8C1D1] hover:text-white"
      >
        <LogOut size={15} aria-hidden="true" /> Sign out
      </button>
    </div>
  )

  return (
    <div className="min-h-screen lg:flex">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col bg-ink text-white lg:flex">
        <div className="px-6 pt-6 pb-1"><Logo /></div>
        <Sidebar />
        {account}
      </aside>

      {/* Mobile top bar and drawer */}
      <div className="flex items-center justify-between bg-ink px-4 py-3 text-white lg:hidden">
        <Logo />
        <button type="button" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)} className="rounded-md p-1.5 hover:bg-ink-soft">
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
      {menuOpen && (
        <div className="flex flex-col bg-ink text-white lg:hidden">
          <Sidebar onNavigate={() => setMenuOpen(false)} />
          {account}
        </div>
      )}

      <main className="min-w-0 flex-1 px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
        <div className="mx-auto max-w-[1180px]">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
