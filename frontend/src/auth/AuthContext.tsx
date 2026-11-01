import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, SESSION_EXPIRED_EVENT } from '../api/client'
import type { Me, Role } from '../api/types'

interface AuthState {
  user: Me | null
  loading: boolean
  login: (username: string, password: string) => Promise<Me>
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
  /** Why the user was signed out without asking (e.g. inactivity), shown on the sign-in page. */
  notice: string | null
}

const AuthContext = createContext<AuthState | null>(null)

async function fetchMe(): Promise<Me | null> {
  try {
    return await api<Me>('/api/auth/me/')
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return null
    throw error
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: fetchMe, staleTime: 60_000 })
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    function expired(event: Event) {
      setNotice((event as CustomEvent<string>).detail)
      queryClient.clear()
      queryClient.setQueryData(['me'], null)
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
  }, [queryClient])

  const loginMutation = useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      api<Me>('/api/auth/login/', { method: 'POST', body: credentials }),
    onSuccess: (user) => {
      setNotice(null)
      queryClient.clear()
      queryClient.setQueryData(['me'], user)
    },
  })

  const logoutMutation = useMutation({
    mutationFn: () => api<void>('/api/auth/logout/', { method: 'POST' }),
    onSettled: () => {
      queryClient.clear()
      queryClient.setQueryData(['me'], null)
    },
  })

  const user = me.data ?? null
  const value: AuthState = {
    user,
    loading: me.isPending,
    login: (username, password) => loginMutation.mutateAsync({ username, password }),
    logout: () => logoutMutation.mutateAsync(),
    hasRole: (...roles) => !!user && roles.includes(user.role),
    notice,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
