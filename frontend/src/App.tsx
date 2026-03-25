import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { AppShell } from '@/components/layout/app-shell'
import { ApplicationDetailPage } from '@/pages/application-detail'
import { ApplicationsPage } from '@/pages/applications'
import { DashboardPage } from '@/pages/dashboard'
import { NotFoundPage } from '@/pages/not-found'
import { QueryPage } from '@/pages/query'
import { SettingsPage } from '@/pages/settings'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'query', element: <QueryPage /> },
      { path: 'applications', element: <ApplicationsPage /> },
      { path: 'applications/:id/run', element: <ApplicationDetailPage /> },
      { path: 'applications/:id', element: <ApplicationDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
