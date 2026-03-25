import { useQuery } from '@tanstack/react-query'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getApplication } from '@/lib/api'
import { loanEventsForStage } from '@/lib/loan-stage-filter'
import type { PipelineSseEvent } from '@/types/pipeline-sse'

type Props = {
  applicationId: string
  stage: string | null
  sseEvents: PipelineSseEvent[]
}

export function StageInspector({ applicationId, stage, sseEvents }: Props) {
  const q = useQuery({
    queryKey: ['application', applicationId],
    queryFn: () => getApplication(applicationId),
  })

  const forStage = stage
    ? sseEvents.filter(
        (e) => e.type === 'progress' && e.stage === stage,
      )
    : []

  const loanFiltered =
    stage && q.data ? loanEventsForStage(stage, q.data.events) : []

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Stage inspector</CardTitle>
        <CardDescription>
          {stage ? (
            <span className="capitalize">Stage: {stage}</span>
          ) : (
            'Click a node in the workflow graph to inspect a stage.'
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {stage && (
          <>
            <div>
              <p className="mb-1 font-medium text-muted-foreground">Pipeline SSE (this run)</p>
              {forStage.length === 0 ? (
                <p className="text-muted-foreground">No progress rows for this stage yet.</p>
              ) : (
                <ul className="max-h-40 space-y-1 overflow-auto rounded border border-border p-2 font-mono text-xs">
                  {forStage.slice(-20).map((e, i) => (
                    <li key={i}>{JSON.stringify(e)}</li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <div className="mb-1 flex items-center gap-2">
                <p className="font-medium text-muted-foreground">Loan stream (filtered)</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void q.refetch()}
                >
                  Reload loan stream
                </Button>
              </div>
              {q.isLoading && <p className="text-muted-foreground">Loading…</p>}
              {q.error && (
                <p className="text-destructive">{(q.error as Error).message}</p>
              )}
              {q.data && loanFiltered.length === 0 && (
                <p className="text-muted-foreground">
                  No matching event types for this stage. Full cross-stream agent I/O may require a
                  timeline API (planned).
                </p>
              )}
              {loanFiltered.length > 0 && (
                <ul className="max-h-48 space-y-2 overflow-auto">
                  {loanFiltered.map((e) => (
                    <li
                      key={`${e.stream_position}-${e.event_type}`}
                      className="rounded border border-border p-2 font-mono text-xs"
                    >
                      <Badge variant="outline" className="mb-1">
                        {e.event_type}
                      </Badge>
                      <pre className="whitespace-pre-wrap break-all text-[11px]">
                        {JSON.stringify(e.payload, null, 2)}
                      </pre>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
