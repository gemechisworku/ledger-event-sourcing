import * as Dialog from '@radix-ui/react-dialog'
import { Menu } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { HealthDot } from '@/components/layout/health-dot'
import { ThemeToggle } from '@/components/layout/theme-toggle'
import { cn } from '@/lib/utils'

const nav = [
  { to: '/', label: 'Dashboard' },
  { to: '/applications', label: 'Applications' },
  { to: '/settings', label: 'Settings' },
]

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1 p-2">
      {nav.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'rounded-xl px-3 py-2 text-sm font-medium transition-all',
              isActive
                ? 'bg-primary/10 text-foreground shadow-sm ring-1 ring-primary/20'
                : 'text-muted-foreground hover:bg-muted/80 hover:text-foreground',
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="hidden w-56 shrink-0 border-r border-sidebar-border bg-sidebar/95 backdrop-blur md:block">
        <div className="flex h-14 items-center border-b border-sidebar-border px-4">
          <Link to="/" className="bg-gradient-to-r from-primary to-primary/70 bg-clip-text font-semibold text-transparent">
            Ledger Workbench
          </Link>
        </div>
        <NavItems />
      </aside>

      <div className="flex min-h-screen flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-2 border-b border-border/80 bg-background/80 px-4 backdrop-blur-md md:px-6">
          <div className="flex items-center gap-2">
            <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
              <Dialog.Trigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                  <Menu className="h-5 w-5" />
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
                <Dialog.Content className="fixed left-0 top-0 z-50 h-full w-64 border-r border-border bg-sidebar p-0 shadow-lg">
                  <div className="flex h-14 items-center border-b border-sidebar-border px-4">
                    <Dialog.Title className="font-semibold">Ledger Workbench</Dialog.Title>
                  </div>
                  <NavItems onNavigate={() => setMobileOpen(false)} />
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
            <span className="font-medium text-foreground md:hidden">Ledger</span>
          </div>
          <div className="flex items-center gap-3">
            <HealthDot />
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
