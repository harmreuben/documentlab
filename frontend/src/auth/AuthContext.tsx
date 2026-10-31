import { createContext, useContext, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import type { Me, Role } from '../api/types'

interface AuthState {
  user: Me | null
  loading: boolean
  login: (username: string, password: string) => Promise<Me>
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
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

  const loginMutation = useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      api<Me>('/api/auth/login/', { method: 'POST', body: credentials }),
    onSuccess: (user) => {
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
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
