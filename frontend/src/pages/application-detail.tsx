import { useQuery } from '@tanstack/react-query'
import { History, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { JobLogPanel } from '@/components/pipeline/job-log-panel'
import { PipelineGraph } from '@/components/pipeline/pipeline-graph'
import { StageInspector } from '@/components/pipeline/stage-inspector'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useJobStream } from '@/hooks/use-job-stream'
import { getApplication, getDecisionHistory, runPipeline } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { PIPELINE_STAGES } from '@/lib/pipeline-stages'
import { getPipelineRuns, recordPipelineRun } from '@/lib/pipeline-history'
import { pushRecentApplicationId } from '@/lib/recent-apps'
import { useUiStore } from '@/stores/ui-store'
import type { PipelineSseEvent } from '@/types/pipeline-sse'

export function ApplicationDetailPage() {
  const { id: rawId } = useParams<{ id: string }>()
  const id = rawId ? decodeURIComponent(rawId) : ''
  const location = useLocation()
  const focusRun = location.pathname.endsWith('/run')
  const runRef = useRef<HTMLDivElement>(null)
  const selectedStage = useUiStore((s) => s.selectedStage)
  const setSelectedStage = useUiStore((s) => s.setSelectedStage)

  const q = useQuery({
    queryKey: ['application', id],
    queryFn: () => getApplication(id),
    enabled: !!id,
  })

  const historyQ = useQuery({
    queryKey: ['decision-history', id],
    queryFn: () => getDecisionHistory(id),
    enabled: !!id,
  })

  useEffect(() => {
    if (id) pushRecentApplicationId(id)
  }, [id])

  useEffect(() => {
    if (focusRun && runRef.current) {
      runRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [focusRun, id])

  const [pick, setPick] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(PIPELINE_STAGES.map((s) => [s, true])),
  )
  const [jobId, setJobId] = useState<string | null>(null)
  const [sseLines, setSseLines] = useState<PipelineSseEvent[]>([])
  const [streamEnded, setStreamEnded] = useState(false)
  const [runBusy, setRunBusy] = useState(false)

  const sseRef = useRef<PipelineSseEvent[]>([])
  const runStartedAtRef = useRef(0)
  const jobIdRef = useRef<string | null>(null)
  const recordedJobRef = useRef<string | null>(null)
  const [runHistoryTick, setRunHistoryTick] = useState(0)

  useEffect(() => {
    jobIdRef.current = jobId
  }, [jobId])

  const appendEvent = useCallback((e: PipelineSseEvent) => {
    setSseLines((prev) => {
      const next = [...prev, e]
      sseRef.current = next
      return next
    })
  }, [])

  const finishRecording = useCallback(
    (kind: 'complete' | 'error') => {
      const jid = jobIdRef.current
      if (!id || !jid) return
      if (recordedJobRef.current === jid) return
      recordedJobRef.current = jid
      const events = sseRef.current
      const lastErr = [...events].reverse().find((ev) => ev.type === 'error') as
        | { type: 'error'; message?: string }
        | undefined
      recordPipelineRun(id, {
        jobId: jid,
        startedAt: runStartedAtRef.current || Date.now(),
        finishedAt: Date.now(),
        status: kind === 'complete' ? 'complete' : 'error',
        eventCount: events.length,
        errorMessage:
          kind === 'error'
            ? lastErr?.message ?? 'Pipeline stream ended with an error'
            : undefined,
      })
      setRunHistoryTick((t) => t + 1)
    },
    [id],
  )

  useJobStream(jobId, {
    onEvent: appendEvent,
    onDone: () => {
      setStreamEnded(true)
      finishRecording('complete')
    },
    onError: () => {
      setStreamEnded(true)
      finishRecording('error')
    },
  })

  const runHistory = useMemo(() => (id ? getPipelineRuns(id) : []), [id, runHistoryTick])

  async function onRun() {
    if (!id) return
    setRunBusy(true)
    recordedJobRef.current = null
    setSseLines([])
    sseRef.current = []
    setStreamEnded(false)
    setJobId(null)
    try {
      const selected = PIPELINE_STAGES.filter((s) => pick[s])
      const stages = selected.length === PIPELINE_STAGES.length ? null : selected
      const res = await runPipeline(id, stages)
      runStartedAtRef.current = Date.now()
      setJobId(res.job_id)
      toast.success(`Job ${res.job_id}`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRunBusy(false)
    }
  }

  if (!id) {
    return <p className="text-destructive">Missing application id.</p>
  }

  return (
    <div className="space-y-8">
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:flex md:items-center md:justify-between md:gap-6 md:p-8">
        <div className="pointer-events-none absolute -right-12 -top-12 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative min-w-0">
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Application command center</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">{id}</p>
        </div>
        <div className="relative mt-4 flex flex-wrap gap-2 md:mt-0">
          <Button variant="secondary" asChild className="shadow-sm">
            <Link to="/applications">All applications</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to={`/applications/${encodeURIComponent(id)}/run`}>Run pipeline</Link>
          </Button>
          <Button variant="outline" asChild className="gap-1.5">
            <Link to={`/query?q=${encodeURIComponent(`Show me the complete decision history of application ${id}`)}`}>
              <Sparkles className="h-3.5 w-3.5" />
              Ask about this app
            </Link>
          </Button>
        </div>
      </div>

      <section ref={runRef} className="space-y-4">
        <h2 className="text-lg font-semibold tracking-tight">Run pipeline</h2>
        <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
          <CardHeader>
            <CardTitle>Stages</CardTitle>
            <CardDescription>
              Uncheck to run a subset. Full pipeline sends all stages (same as backend default).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-3">
              {PIPELINE_STAGES.map((s) => (
                <label
                  key={s}
                  className="flex cursor-pointer items-center gap-2 rounded-full border border-border/80 bg-muted/40 px-3 py-1.5 text-sm capitalize shadow-sm transition-colors hover:bg-muted/70"
                >
                  <input
                    type="checkbox"
                    className="accent-primary"
                    checked={pick[s] ?? false}
                    onChange={(e) => setPick((p) => ({ ...p, [s]: e.target.checked }))}
                  />
                  {s}
                </label>
              ))}
            </div>
            <Button type="button" onClick={() => void onRun()} disabled={runBusy} className="shadow-sm">
              {runBusy ? 'Starting…' : 'Run'}
            </Button>
            {jobId && (
              <p className="text-xs text-muted-foreground">
                Job <span className="font-mono">{jobId}</span>
                {streamEnded ? ' · ended' : ' · streaming'}
              </p>
            )}
          </CardContent>
        </Card>
      </section>

      {runHistory.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold tracking-tight">Run history</h2>
            <span className="text-xs text-muted-foreground">(this browser)</span>
          </div>
          <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
            <CardContent className="p-0">
              <ul className="divide-y divide-border/60">
                {runHistory.map((r) => (
                  <li key={r.jobId} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-3">
                    <span className="font-mono text-sm text-foreground">{r.jobId}</span>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={r.status === 'error' ? 'destructive' : 'success'}>{r.status}</Badge>
                      <span className="text-xs text-muted-foreground">{r.eventCount} SSE events</span>
                      <span className="text-xs text-muted-foreground">{formatRelativeTime(r.finishedAt)}</span>
                    </div>
                    {r.errorMessage && (
                      <p className="w-full text-sm text-destructive">
                        {r.errorMessage}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold tracking-tight">Workflow</h2>
        <PipelineGraph
          sseEvents={sseLines}
          selectedStage={selectedStage}
          onSelectStage={setSelectedStage}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <StageInspector applicationId={id} stage={selectedStage} sseEvents={sseLines} />
        <div className="space-y-2">
          <h2 className="text-lg font-semibold tracking-tight">Live log</h2>
          <JobLogPanel
            lines={sseLines}
            streamEnded={streamEnded}
            onClear={() => {
              setSseLines([])
              sseRef.current = []
            }}
          />
        </div>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">Decision history</h2>
          <Button type="button" variant="outline" size="sm" onClick={() => void historyQ.refetch()}>
            Reload
          </Button>
        </div>
        {historyQ.isLoading && <p className="text-muted-foreground">Loading decision history…</p>}
        {historyQ.error && <p className="text-destructive">{(historyQ.error as Error).message}</p>}
        {historyQ.data && (
          <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                {historyQ.data.total_events} events across {historyQ.data.streams_queried.length} streams
              </CardTitle>
              {historyQ.data.integrity && (
                <CardDescription className="flex items-center gap-2">
                  <Badge variant={historyQ.data.integrity.chain_valid ? 'success' : 'destructive'}>
                    {historyQ.data.integrity.chain_valid ? 'Chain valid' : 'Chain broken'}
                  </Badge>
                  <Badge variant={historyQ.data.integrity.tamper_detected ? 'destructive' : 'success'}>
                    {historyQ.data.integrity.tamper_detected ? 'Tamper detected' : 'No tampering'}
                  </Badge>
                  <span className="text-xs">{historyQ.data.integrity.events_verified} events verified</span>
                </CardDescription>
              )}
            </CardHeader>
            <CardContent className="p-0">
              <ul className="max-h-[500px] divide-y divide-border/60 overflow-auto">
                {historyQ.data.events.map((ev, i) => (
                  <li key={`${ev.stream_id}-${ev.stream_position}-${i}`} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-mono text-[10px]">{ev.stream_id}</Badge>
                      <span className="text-sm font-medium">{ev.event_type}</span>
                      <span className="font-mono text-xs text-muted-foreground">#{ev.stream_position}</span>
                      {ev.recorded_at && (
                        <span className="text-xs text-muted-foreground">{new Date(ev.recorded_at).toLocaleString()}</span>
                      )}
                    </div>
                    {ev.payload && (
                      <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all text-xs text-muted-foreground">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">Loan stream</h2>
          <Button type="button" variant="outline" size="sm" onClick={() => void q.refetch()}>
            Reload
          </Button>
        </div>
        {q.isLoading && <p className="text-muted-foreground">Loading…</p>}
        {q.error && <p className="text-destructive">{(q.error as Error).message}</p>}
        {q.data && (
          <div className="space-y-2 overflow-hidden rounded-xl border border-border/80 bg-card/50 shadow-sm ring-1 ring-border/40">
            <div className="border-b border-border/80 bg-muted/30 px-4 py-2.5 text-sm text-muted-foreground">
              {q.data.event_count} events on <span className="font-mono">{q.data.stream_id}</span>
            </div>
            <ul className="max-h-[480px] space-y-2 overflow-auto p-4">
              {q.data.events.map((e) => (
                <li
                  key={e.stream_position}
                  className="rounded-lg border border-border/60 bg-card/80 p-3 shadow-sm"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">
                      #{e.stream_position}
                    </span>
                    <span className="text-sm font-medium">{e.event_type}</span>
                  </div>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs text-muted-foreground">
                    {JSON.stringify(e.payload, null, 2)}
                  </pre>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  )
}
