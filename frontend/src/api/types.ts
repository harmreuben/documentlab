export type Role = 'ADMINISTRATOR' | 'ANALYST' | 'REVIEWER' | 'DEVELOPER' | 'READ_ONLY'

export const ROLE_LABELS: Record<Role, string> = {
  ADMINISTRATOR: 'Administrator',
  ANALYST: 'Analyst',
  REVIEWER: 'Reviewer',
  DEVELOPER: 'Developer',
  READ_ONLY: 'Read-only user',
}

export interface Me {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  role: Role
  role_label: string
  last_login: string | null
}

export interface ManagedUser extends Omit<Me, 'role_label'> {
  role_label: string
  is_active: boolean
  date_joined: string
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface AuditEvent {
  id: number
  created_at: string
  username: string
  action: string
  object_type: string
  object_id: string
  ip_address: string | null
  user_agent: string
  metadata: Record<string, unknown>
}

export interface ModuleInfo {
  key: string
  name: string
  phase: number
  status: 'available' | 'planned'
}

export interface DashboardSummary {
  scope: 'system' | 'personal'
  version: string
  generated_at: string
  counts: {
    events_24h: number
    logins_7d: number
    failed_logins_7d: number | null
    documents_processed: number | null
    barcodes_generated: number | null
    barcodes_failed_verification?: number
    barcodes_decoded: number | null
    pending_reviews: number | null
  }
  users: { total: number; active: number; by_role: Record<Role, number> } | null
  activity: { date: string; events: number }[]
  recent_activity: { id: number; created_at: string; username: string; action: string }[]
  modules: ModuleInfo[]
}

export interface Health {
  status: string
  version: string
  database: string
}
