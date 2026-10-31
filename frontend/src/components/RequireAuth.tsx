import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABELS, type Role } from '../api/types'
import { Loading, PageHeader } from './ui'

/** Sends signed-out visitors to the login page; optionally limits a page to certain roles. */
export function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="p-10"><Loading label="Checking your session" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(user.role)) {
    return (
      <PageHeader
        title="You don't have access to this page"
        description={`This page is for ${roles.map((r) => ROLE_LABELS[r].toLowerCase()).join(' and ')} accounts. Ask an administrator if you need access.`}
      />
    )
  }
  return <>{children}</>
}
