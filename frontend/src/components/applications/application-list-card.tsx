import { ChevronRight, History, Layers } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { formatShortDate, formatRelativeTime } from '@/lib/format'
import type { ApplicationListItem } from '@/lib/api'
import type { PipelineRunHistoryEntry } from '@/lib/pipeline-history'
import { cn } from '@/lib/utils'

function stateBadge(state: string) {
  const u = state.toUpperCase()
  if (u.includes('DECLIN') || u.includes('FAIL')) return 'destructive' as const
  if (u.includes('APPROV') || u.includes('COMPLETE')) return 'success' as const
  if (u.includes('PENDING') || u.includes('SUBMIT')) return 'warning' as const
  if (u === 'LOCAL') return 'outline' as const
  return 'secondary' as const
}

type Props = {
  app: ApplicationListItem
  runs: PipelineRunHistoryEntry[]
  localOnly?: boolean
}

export function ApplicationListCard({ app, runs, localOnly }: Props) {
  const hasErrorRun = runs.some((r) => r.status === 'error')

  return (
    <Link
      to={`/applications/${encodeURIComponent(app.application_id)}`}
      className="group block outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-2xl"
    >
      <Card
        className={cn(
          'overflow-hidden border-0 bg-card/80 shadow-md ring-1 ring-border/60 transition-all duration-200',
          'hover:shadow-xl hover:ring-primary/25 hover:-translate-y-0.5',
        )}
      >
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate font-mono text-base font-semibold tracking-tight text-foreground">
                  {app.application_id}
                </span>
                <Badge variant={stateBadge(app.state)}>{app.state}</Badge>
                {localOnly && (
                  <Badge variant="outline" className="text-xs">
                    Not in projection
                  </Badge>
                )}
                {hasErrorRun && (
                  <Badge variant="destructive" className="text-xs">
                    Run error (browser)
                  </Badge>
                )}
              </div>
              {!localOnly && (
                <p className="text-sm text-muted-foreground">
                  {app.applicant_id ? (
                    <>
                      Applicant <span className="font-medium text-foreground/90">{app.applicant_id}</span>
                      {app.requested_amount_usd && (
                        <> · <span className="tabular-nums">${app.requested_amount_usd}</span></>
                      )}
                    </>
                  ) : (
                    '—'
                  )}
                </p>
              )}
            </div>
            <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
          </div>

          {!localOnly && (
            <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
              <div className="flex items-center gap-2 rounded-lg bg-muted/50 px-2 py-1.5">
                <Layers className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Last event</span>
                <span className="truncate font-medium text-foreground">
                  {app.last_event_type ?? '—'}
                </span>
              </div>
              <div className="rounded-lg bg-muted/50 px-2 py-1.5 text-muted-foreground">
                <span className="text-[10px] uppercase tracking-wide">Updated</span>
                <div className="font-medium text-foreground">{formatShortDate(app.last_event_at ?? app.updated_at)}</div>
              </div>
              {app.decision && (
                <div className="rounded-lg bg-emerald-500/10 px-2 py-1.5 sm:col-span-2">
                  <span className="text-muted-foreground">Decision </span>
                  <span className="font-semibold text-emerald-700 dark:text-emerald-400">{app.decision}</span>
                </div>
              )}
              {app.compliance_status && (
                <div className="rounded-lg bg-muted/50 px-2 py-1.5 sm:col-span-2">
                  <span className="text-muted-foreground">Compliance </span>
                  <span className="font-medium">{app.compliance_status}</span>
                  {app.risk_tier && (
                    <span className="text-muted-foreground"> · Risk {app.risk_tier}</span>
                  )}
                </div>
              )}
              <div className="text-muted-foreground sm:col-span-2">
                Loan stream revision <span className="font-medium text-foreground">v{app.stream_version}</span>
                {app.fraud_score != null && (
                  <span> · Fraud score {app.fraud_score}</span>
                )}
              </div>
            </dl>
          )}

          {runs.length > 0 && (
            <div className="mt-4 border-t border-border/60 pt-3">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <History className="h-3.5 w-3.5" />
                Pipeline runs (this browser)
              </div>
              <ul className="space-y-1.5">
                {runs.slice(0, 5).map((r) => (
                  <li
                    key={r.jobId}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1.5 text-xs"
                  >
                    <span className="font-mono text-[11px] text-foreground/90">{r.jobId.slice(0, 8)}…</span>
                    <Badge variant={r.status === 'error' ? 'destructive' : 'success'} className="text-[10px]">
                      {r.status}
                    </Badge>
                    <span className="text-muted-foreground">{r.eventCount} SSE events</span>
                    <span className="text-muted-foreground">{formatRelativeTime(r.finishedAt)}</span>
                    {r.errorMessage && (
                      <span className="w-full truncate text-destructive" title={r.errorMessage}>
                        {r.errorMessage}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  )
}
