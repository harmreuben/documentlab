import {
  Barcode, ClipboardCheck, FileSearch, FlaskConical, LayoutDashboard, ListChecks,
  ScanLine, ScrollText, Settings, Users, type LucideIcon,
} from 'lucide-react'
import type { Role } from './api/types'

export interface NavItem {
  key: string // matches the module key from the backend
  label: string
  path: string
  icon: LucideIcon
  description: string
  roles?: Role[] // omitted = every role
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAVIGATION: NavGroup[] = [
  {
    label: 'Overview',
    items: [
      { key: 'dashboard', label: 'Dashboard', path: '/', icon: LayoutDashboard,
        description: 'Activity and system status at a glance.' },
    ],
  },
  {
    label: 'Workspaces',
    items: [
      { key: 'generator', label: 'Barcode Generator', path: '/generator', icon: Barcode,
        description: 'Create QR, Code 128, Code 39, EAN, UPC and generic PDF417 codes, singly or in batches.' },
      { key: 'analyzer', label: 'Barcode Analyzer', path: '/analyzer', icon: ScanLine,
        description: 'Upload images or PDFs, decode barcodes and inspect image quality.' },
      { key: 'documents', label: 'Document Analysis', path: '/documents', icon: FileSearch,
        description: 'OCR, passport MRZ checks, SSN format checks and cross-document comparison.' },
      { key: 'test_lab', label: 'Testing Laboratory', path: '/test-lab', icon: FlaskConical,
        description: 'Run fixtures and regression tests, and compare expected with actual results.' },
    ],
  },
  {
    label: 'Quality',
    items: [
      { key: 'rules', label: 'Validation Rules', path: '/rules', icon: ListChecks,
        description: 'Every validation rule, its version, severity and test coverage.' },
      { key: 'reports', label: 'Reports', path: '/reports', icon: ClipboardCheck,
        description: 'PDF and CSV reports of analyses, tests and validation results.' },
    ],
  },
  {
    label: 'Administration',
    items: [
      { key: 'audit', label: 'Audit Logs', path: '/audit', icon: ScrollText, roles: ['ADMINISTRATOR'],
        description: 'Every sign-in and change, with who did it and when.' },
      { key: 'users', label: 'User Management', path: '/users', icon: Users, roles: ['ADMINISTRATOR'],
        description: 'Create accounts, assign roles and deactivate users.' },
    ],
  },
  {
    label: 'Account',
    items: [
      { key: 'settings', label: 'Settings', path: '/settings', icon: Settings,
        description: 'Your account and system information.' },
    ],
  },
]

export const ALL_NAV_ITEMS = NAVIGATION.flatMap((group) => group.items)

export function visibleNavigation(role: Role | undefined): NavGroup[] {
  return NAVIGATION
    .map((group) => ({ ...group, items: group.items.filter((i) => !i.roles || (role && i.roles.includes(role))) }))
    .filter((group) => group.items.length > 0)
}
