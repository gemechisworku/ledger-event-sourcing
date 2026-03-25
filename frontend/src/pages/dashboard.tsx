import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getHealth } from '@/lib/api'

export function DashboardPage() {
  const q = useQuery({ queryKey: ['health'], queryFn: getHealth })

  return (
    <div className="space-y-8">
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="pointer-events-none absolute -left-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2 text-primary">
              <Activity className="h-5 w-5" />
              <span className="text-xs font-semibold uppercase tracking-widest">Overview</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
            <p className="mt-1 max-w-xl text-muted-foreground">
              Operational view of the Ledger BFF and quick entry points.
            </p>
          </div>
          <Button asChild className="shadow-sm">
            <Link to="/applications" className="gap-2">
              Applications
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
          <CardHeader>
            <CardTitle>Event store</CardTitle>
            <CardDescription>
              From <code className="text-xs">GET /health</code>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {q.isLoading && <p className="text-muted-foreground">Loading…</p>}
            {q.isError && <p className="text-destructive">{(q.error as Error).message}</p>}
            {q.data && (
              <>
                <p>
                  <span className="text-muted-foreground">Database:</span> {q.data.database}
                </p>
                <p>
                  <span className="text-muted-foreground">Store pool:</span>{' '}
                  {q.data.store_pool ? 'yes' : 'no'}
                </p>
              </>
            )}
          </CardContent>
        </Card>
        <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
          <CardHeader>
            <CardTitle>Applications</CardTitle>
            <CardDescription>Browse ledger rows, run pipelines, and inspect streams.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button asChild variant="secondary" className="shadow-sm">
              <Link to="/applications">Open applications</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/applications">New application</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
