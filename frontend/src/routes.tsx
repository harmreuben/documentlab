import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { Link, type RouteObject } from 'react-router'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { Loading, PageHeader } from './components/ui'
import { ALL_NAV_ITEMS } from './navigation'
import { LoginPage } from './pages/LoginPage'
import { ModulePage } from './pages/ModulePage'

// Each page is downloaded only when first opened, which keeps the first load small.
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  const Component: ComponentType = lazy(() => load().then((m) => ({ default: m[name] as ComponentType })))
  return <Suspense fallback={<Loading />}><Component /></Suspense>
}

function adminOnly(element: ReactNode) {
  return <RequireAuth roles={['ADMINISTRATOR']}>{element}</RequireAuth>
}

// Workspaces that are not built yet. Each moves to a real page as its phase is finished.
const PLANNED = ['analyzer', 'documents', 'test_lab', 'rules', 'reports']

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth><Layout /></RequireAuth>,
    children: [
      { index: true, element: page(() => import('./pages/DashboardPage'), 'DashboardPage') },
      { path: 'audit', element: adminOnly(page(() => import('./pages/AuditLogPage'), 'AuditLogPage')) },
      { path: 'users', element: adminOnly(page(() => import('./pages/UsersPage'), 'UsersPage')) },
      { path: 'settings', element: page(() => import('./pages/SettingsPage'), 'SettingsPage') },
      { path: 'generator', element: page(() => import('./pages/generator/GeneratorPage'), 'GeneratorPage') },
      ...ALL_NAV_ITEMS.filter((item) => PLANNED.includes(item.key)).map((item) => ({
        path: item.path.slice(1),
        element: <ModulePage item={item} />,
      })),
      {
        path: '*',
        element: (
          <>
            <PageHeader title="Page not found" description="That address doesn't match any page in DocumentLab." />
            <Link className="text-sm text-electric hover:underline" to="/">Go to the dashboard</Link>
          </>
        ),
      },
    ],
  },
]
