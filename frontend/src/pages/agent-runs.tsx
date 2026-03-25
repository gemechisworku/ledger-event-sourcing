import { useQuery } from '@tanstack/react-query'
import { Bot, Loader2, Play, RefreshCw, Skull, Zap } from 'lucide-react'
import { useCallback, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  crashSimulation,
  listApplications,
  recoverAgent,
  runAgent,
  runConcurrentCredit,
} from '@/lib/api'

const STAGES = ['document', 'credit', 'fraud', 'compliance', 'decision'] as const

function JsonBlock({ value, maxH = '24rem' }: { value: unknown; maxH?: string }) {
  return (
    <pre
      className="overflow-auto rounded-lg border border-border/60 bg-muted/30 p-3 text-xs leading-relaxed"
      style={{ maxHeight: maxH }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function AppPicker({
  value,
  onChange,
  label,
}: {
  value: string
  onChange: (v: string) => void
  label?: string
}) {
  const q = useQuery({
    queryKey: ['applications-list'],
    queryFn: () => listApplications({ limit: 200 }),
    staleTime: 30_000,
  })
  const apps = (q.data?.applications ?? []).filter(
    (a) => a.state !== 'LOCAL',
  )

  return (
    <div className="space-y-1">
      <Label>{label ?? 'Application'}</Label>
      <div className="flex items-center gap-2">
        <select
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select an application…</option>
          {apps.map((a) => (
            <option key={a.application_id} value={a.application_id}>
              {a.application_id} — {a.state ?? 'submitted'}{' '}
              {a.decision ? `(${a.decision})` : ''}
            </option>
          ))}
        </select>
        {q.isFetching ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
      </div>
      <Input
        placeholder="Or type application_id manually"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1"
      />
    </div>
  )
}

function NarrativeBox({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm leading-relaxed">
      {text}
    </div>
  )
}

export function AgentRunsPage() {
  // ── Single agent run ──
  const [singleApp, setSingleApp] = useState('')
  const [singleStage, setSingleStage] = useState<string>('credit')
  const [singleResult, setSingleResult] = useState<Record<string, unknown> | null>(null)
  const [singleLoading, setSingleLoading] = useState(false)
  const [singleErr, setSingleErr] = useState<string | null>(null)

  const handleRunSingle = useCallback(async () => {
    if (!singleApp.trim()) { setSingleErr('Select an application'); return }
    setSingleLoading(true); setSingleErr(null); setSingleResult(null)
    try {
      setSingleResult(await runAgent(singleApp.trim(), singleStage))
    } catch (e) { setSingleErr((e as Error).message) }
    finally { setSingleLoading(false) }
  }, [singleApp, singleStage])

  // ── Concurrent credit ──
  const [occApp, setOccApp] = useState('')
  const [occResult, setOccResult] = useState<Record<string, unknown> | null>(null)
  const [occLoading, setOccLoading] = useState(false)
  const [occErr, setOccErr] = useState<string | null>(null)

  const handleOcc = useCallback(async () => {
    if (!occApp.trim()) { setOccErr('Select an application'); return }
    setOccLoading(true); setOccErr(null); setOccResult(null)
    try {
      setOccResult(await runConcurrentCredit(occApp.trim()))
    } catch (e) { setOccErr((e as Error).message) }
    finally { setOccLoading(false) }
  }, [occApp])

  // ── Crash & recover ──
  const [crashApp, setCrashApp] = useState('')
  const [crashResult, setCrashResult] = useState<Record<string, unknown> | null>(null)
  const [recoverResult, setRecoverResult] = useState<Record<string, unknown> | null>(null)
  const [crashLoading, setCrashLoading] = useState(false)
  const [crashErr, setCrashErr] = useState<string | null>(null)

  const handleCrash = useCallback(async () => {
    if (!crashApp.trim()) { setCrashErr('Select an application'); return }
    setCrashLoading(true); setCrashErr(null); setCrashResult(null); setRecoverResult(null)
    try {
      setCrashResult(await crashSimulation(crashApp.trim()))
    } catch (e) { setCrashErr((e as Error).message) }
    finally { setCrashLoading(false) }
  }, [crashApp])

  const crashSessionId = (crashResult as { session_id?: string })?.session_id

  const handleRecover = useCallback(async () => {
    if (!crashSessionId || !crashApp.trim()) return
    setCrashLoading(true); setCrashErr(null); setRecoverResult(null)
    try {
      setRecoverResult(
        await recoverAgent({
          application_id: crashApp.trim(),
          session_id: crashSessionId,
          resume: true,
        }),
      )
    } catch (e) { setCrashErr((e as Error).message) }
    finally { setCrashLoading(false) }
  }, [crashApp, crashSessionId])

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="flex items-start gap-3">
          <Bot className="mt-1 h-8 w-8 shrink-0 text-primary" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-primary">Operations</p>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Agent Runs</h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              Run individual LangGraph agents against loan applications, test concurrent credit
              analysis with optimistic concurrency, and simulate crash recovery with Gas Town.
            </p>
          </div>
        </div>
      </div>

      {/* ── Run a single agent ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Play className="h-5 w-5 text-primary" />
            <CardTitle>Run individual agent</CardTitle>
          </div>
          <CardDescription>
            Pick an application and a pipeline stage. The corresponding LangGraph agent runs
            end-to-end and writes real events to the ledger.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <AppPicker value={singleApp} onChange={setSingleApp} />
            <div className="space-y-1">
              <Label>Stage</Label>
              <select
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={singleStage}
                onChange={(e) => setSingleStage(e.target.value)}
              >
                {STAGES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
          <Button onClick={handleRunSingle} disabled={singleLoading}>
            {singleLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
            Run {singleStage} agent
          </Button>
          {singleErr ? <p className="text-sm text-destructive">{singleErr}</p> : null}
          {singleResult ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant={(singleResult as { ok?: boolean }).ok ? 'default' : 'destructive'}>
                  {(singleResult as { ok?: boolean }).ok ? 'Succeeded' : 'Failed'}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  Session: {(singleResult as { session_id?: string }).session_id ?? '—'} ·{' '}
                  {(singleResult as { duration_ms?: number }).duration_ms ?? 0}ms
                </span>
              </div>
              <JsonBlock value={singleResult} />
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── Concurrent credit (OCC) ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            <CardTitle>Concurrent credit analysis</CardTitle>
          </div>
          <CardDescription>
            Two CreditAnalysisAgents race on the same application. One writes{' '}
            <code className="text-xs">CreditAnalysisCompleted</code> to the credit stream; the
            other hits <code className="text-xs">OptimisticConcurrencyError</code>, retries, and
            yields. Document processing runs automatically if needed.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <AppPicker
            value={occApp}
            onChange={setOccApp}
            label="Application (no existing CreditAnalysisCompleted)"
          />
          <Button onClick={handleOcc} disabled={occLoading}>
            {occLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Zap className="mr-2 h-4 w-4" />}
            Run concurrent credit analysis
          </Button>
          {occErr ? <p className="text-sm text-destructive">{occErr}</p> : null}
          {occResult ? (
            <div className="space-y-3">
              {(occResult as { summary?: string }).summary ? (
                <NarrativeBox text={(occResult as { summary: string }).summary} />
              ) : null}
              {Array.isArray((occResult as { occ_events?: unknown[] }).occ_events) &&
              ((occResult as { occ_events: unknown[] }).occ_events).length > 0 ? (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    OCC events captured during the race
                  </p>
                  <JsonBlock
                    value={(occResult as { occ_events: unknown[] }).occ_events}
                    maxH="12rem"
                  />
                </div>
              ) : null}
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium text-muted-foreground group-open:mb-2">
                  Full response
                </summary>
                <JsonBlock value={occResult} />
              </details>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── Crash & recover ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Skull className="h-5 w-5 text-primary" />
            <CardTitle>Agent crash &amp; Gas Town recovery</CardTitle>
          </div>
          <CardDescription>
            Runs a FraudDetectionAgent that crashes mid-session (after writing{' '}
            <code className="text-xs">FraudScreeningInitiated</code> but before{' '}
            <code className="text-xs">FraudScreeningCompleted</code>). Then reconstructs
            context from the ledger and resumes the agent with a new session.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <AppPicker value={crashApp} onChange={setCrashApp} />
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleCrash} disabled={crashLoading} variant="destructive">
              {crashLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Skull className="mr-2 h-4 w-4" />}
              Simulate crash
            </Button>
            <Button
              onClick={handleRecover}
              disabled={crashLoading || !crashSessionId}
              variant="default"
            >
              {crashLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Reconstruct &amp; resume
            </Button>
          </div>
          {crashErr ? <p className="text-sm text-destructive">{crashErr}</p> : null}
          {crashResult ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="destructive">Crashed</Badge>
                <span className="text-xs text-muted-foreground">
                  Session: {crashSessionId ?? '—'}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {(crashResult as { crash_error?: string }).crash_error}
              </p>
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium text-muted-foreground group-open:mb-2">
                  Crash details
                </summary>
                <JsonBlock value={crashResult} />
              </details>
            </div>
          ) : null}
          {recoverResult ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="default">Recovered</Badge>
                <span className="text-xs text-muted-foreground">
                  Resumed session:{' '}
                  {(recoverResult as { resumed_session_id?: string }).resumed_session_id ?? '—'}
                </span>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  Reconstructed context
                </p>
                <JsonBlock
                  value={(recoverResult as { reconstructed_context?: unknown }).reconstructed_context}
                  maxH="14rem"
                />
              </div>
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium text-muted-foreground group-open:mb-2">
                  Full recovery details
                </summary>
                <JsonBlock value={recoverResult} />
              </details>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
