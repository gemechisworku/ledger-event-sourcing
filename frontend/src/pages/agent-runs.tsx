import { useQuery } from '@tanstack/react-query'
import { Bot, Hand, Loader2, Play, RefreshCw, Zap } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { AgentSseEvent } from '@/hooks/use-agent-stream'
import { useAgentStream } from '@/hooks/use-agent-stream'
import {
  interruptAgent,
  listApplications,
  recoverAgent,
  runAgent,
  runDualAgents,
} from '@/lib/api'

const STAGES = ['document', 'credit', 'fraud', 'compliance', 'decision'] as const
const AGENT_TYPE_MAP: Record<string, string> = {
  document: 'document_processing',
  credit: 'credit_analysis',
  fraud: 'fraud_detection',
  compliance: 'compliance',
  decision: 'decision_orchestrator',
}

/* ── Reusable log panel ── */

function LogPanel({ logs, maxH = '24rem' }: { logs: AgentSseEvent[]; maxH?: string }) {
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  if (logs.length === 0) return null
  return (
    <div
      className="overflow-auto rounded-lg border border-border/60 bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-300"
      style={{ maxHeight: maxH }}
    >
      {logs.map((ev, i) => (
        <LogLine key={i} ev={ev} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

function LogLine({ ev }: { ev: AgentSseEvent }) {
  const ts = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''
  const prefix = ev.label ? `[${ev.label}] ` : ''

  if (ev.type === 'event_written') {
    return (
      <div className="text-emerald-400">
        <span className="text-zinc-500">{ts} </span>
        {prefix}EVENT {ev.event_type}{' '}
        <span className="text-zinc-500">→ {ev.stream_id}</span>
      </div>
    )
  }
  if (ev.type === 'occ_error') {
    return (
      <div className="font-semibold text-amber-400">
        <span className="text-zinc-500">{ts} </span>
        {prefix}OCC CONFLICT on {ev.stream_id} — expected v{ev.expected_version}, actual v
        {ev.actual_version}
        {ev.event_types?.length ? ` (writing: ${ev.event_types.join(', ')})` : ''}
      </div>
    )
  }
  if (ev.type === 'agent_done') {
    const color = ev.ok ? 'text-emerald-400' : 'text-red-400'
    return (
      <div className={color}>
        <span className="text-zinc-500">{ts} </span>
        {ev.message}
      </div>
    )
  }
  if (ev.type === 'complete') {
    return (
      <div className="mt-1 font-semibold text-emerald-300">
        <span className="text-zinc-500">{ts} </span>
        {ev.message ?? 'Done'}
      </div>
    )
  }
  if (ev.type === 'interrupted') {
    return (
      <div className="mt-1 font-semibold text-yellow-400">
        <span className="text-zinc-500">{ts} </span>
        INTERRUPTED — {ev.message}
      </div>
    )
  }
  if (ev.type === 'error') {
    return (
      <div className="mt-1 font-semibold text-red-400">
        <span className="text-zinc-500">{ts} </span>
        ERROR: {ev.message}
      </div>
    )
  }
  return (
    <div>
      <span className="text-zinc-500">{ts} </span>
      {prefix}
      {ev.message ?? JSON.stringify(ev)}
    </div>
  )
}

/* ── Application picker (shared) ── */

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
  const apps = (q.data?.applications ?? []).filter((a) => a.state !== 'LOCAL')

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
        {q.isFetching ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : null}
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

function StagePicker({
  value,
  onChange,
  label,
}: {
  value: string
  onChange: (v: string) => void
  label?: string
}) {
  return (
    <div className="space-y-1">
      <Label>{label ?? 'Stage'}</Label>
      <select
        className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {STAGES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: 'default' | 'destructive' | 'outline' | 'secondary'; text: string }> = {
    idle: { variant: 'secondary', text: 'Idle' },
    running: { variant: 'outline', text: 'Running…' },
    done: { variant: 'default', text: 'Completed' },
    error: { variant: 'destructive', text: 'Failed' },
    interrupted: { variant: 'secondary', text: 'Interrupted' },
  }
  const m = map[status] ?? map.idle
  return <Badge variant={m.variant}>{m.text}</Badge>
}

/* ── Page ── */

export function AgentRunsPage() {
  // ── Single agent run ──
  const [singleApp, setSingleApp] = useState('')
  const [singleStage, setSingleStage] = useState<string>('credit')
  const [singleErr, setSingleErr] = useState<string | null>(null)
  const single = useAgentStream()

  const handleRunSingle = useCallback(async () => {
    if (!singleApp.trim()) {
      setSingleErr('Select an application')
      return
    }
    setSingleErr(null)
    try {
      const { job_id } = await runAgent(singleApp.trim(), singleStage)
      single.start(job_id)
    } catch (e) {
      setSingleErr((e as Error).message)
    }
  }, [singleApp, singleStage, single])

  // ── Concurrent dual agent run ──
  const [dualApp, setDualApp] = useState('')
  const [dualStage, setDualStage] = useState<string>('credit')
  const [dualErr, setDualErr] = useState<string | null>(null)
  const dual = useAgentStream()

  const handleRunDual = useCallback(async () => {
    if (!dualApp.trim()) {
      setDualErr('Select an application')
      return
    }
    setDualErr(null)
    try {
      const { job_id } = await runDualAgents(dualApp.trim(), dualStage)
      dual.start(job_id)
    } catch (e) {
      setDualErr((e as Error).message)
    }
  }, [dualApp, dualStage, dual])

  // ── Gas Town: run → interrupt → recover ──
  const [gasApp, setGasApp] = useState('')
  const [gasStage, setGasStage] = useState<string>('credit')
  const [gasErr, setGasErr] = useState<string | null>(null)
  const [recoverResult, setRecoverResult] = useState<Record<string, unknown> | null>(null)
  const [recoverLoading, setRecoverLoading] = useState(false)
  const gas = useAgentStream()

  const handleRunGas = useCallback(async () => {
    if (!gasApp.trim()) {
      setGasErr('Select an application')
      return
    }
    setGasErr(null)
    setRecoverResult(null)
    try {
      const { job_id } = await runAgent(gasApp.trim(), gasStage)
      gas.start(job_id)
    } catch (e) {
      setGasErr((e as Error).message)
    }
  }, [gasApp, gasStage, gas])

  const handleInterrupt = useCallback(async () => {
    if (!gas.jobId) return
    try {
      await interruptAgent(gas.jobId)
    } catch (e) {
      setGasErr((e as Error).message)
    }
  }, [gas.jobId])

  const gasSessionId = gas.logs.find((l) => l.session_id)?.session_id ?? null

  const handleRecover = useCallback(async () => {
    if (!gasSessionId) {
      setGasErr('No session to recover — run and interrupt an agent first')
      return
    }
    setRecoverLoading(true)
    setGasErr(null)
    try {
      const res = await recoverAgent({
        session_id: gasSessionId,
        agent_type: AGENT_TYPE_MAP[gasStage] ?? gasStage,
      })
      setRecoverResult(res)
    } catch (e) {
      setGasErr((e as Error).message)
    } finally {
      setRecoverLoading(false)
    }
  }, [gasSessionId, gasStage])

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="flex items-start gap-3">
          <Bot className="mt-1 h-8 w-8 shrink-0 text-primary" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-primary">
              Operations
            </p>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Agent Runs</h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              Run LangGraph agents against loan applications with live event streaming. Test
              concurrent runs for OCC conflicts, or interrupt a running agent and recover with Gas
              Town.
            </p>
          </div>
        </div>
      </div>

      {/* ── Run a single agent ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Play className="h-5 w-5 text-primary" />
            <CardTitle>Run agent</CardTitle>
            <StatusBadge status={single.status} />
          </div>
          <CardDescription>
            Pick an application and a pipeline stage. The agent runs end-to-end and all ledger writes
            appear in the log below in real time.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <AppPicker value={singleApp} onChange={setSingleApp} />
            <StagePicker value={singleStage} onChange={setSingleStage} />
          </div>
          <Button
            onClick={handleRunSingle}
            disabled={single.status === 'running'}
          >
            {single.status === 'running' ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Run {singleStage} agent
          </Button>
          {singleErr ? <p className="text-sm text-destructive">{singleErr}</p> : null}
          <LogPanel logs={single.logs} />
        </CardContent>
      </Card>

      {/* ── Concurrent dual agent run (OCC) ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            <CardTitle>Concurrent analysis (OCC)</CardTitle>
            <StatusBadge status={dual.status} />
          </div>
          <CardDescription>
            Two instances of the same agent race on the same application and stage. They both write
            to the same domain stream — one wins, the other hits{' '}
            <code className="text-xs">OptimisticConcurrencyError</code> and retries. Watch the OCC
            conflicts appear in the log in real time.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <AppPicker value={dualApp} onChange={setDualApp} label="Application (both agents)" />
            <StagePicker value={dualStage} onChange={setDualStage} label="Stage (both agents)" />
          </div>
          <Button
            onClick={handleRunDual}
            disabled={dual.status === 'running'}
          >
            {dual.status === 'running' ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Zap className="mr-2 h-4 w-4" />
            )}
            Run two {dualStage} agents in parallel
          </Button>
          {dualErr ? <p className="text-sm text-destructive">{dualErr}</p> : null}
          <LogPanel logs={dual.logs} maxH="30rem" />
        </CardContent>
      </Card>

      {/* ── Gas Town: Run → Interrupt → Recover ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5 text-primary" />
            <CardTitle>Gas Town recovery</CardTitle>
            <StatusBadge status={gas.status} />
          </div>
          <CardDescription>
            Start any agent, then interrupt it mid-execution. The partial events remain in the
            ledger. Use <strong>Recover</strong> to reconstruct the agent's context from those
            events — demonstrating the Gas Town persistent ledger pattern.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <AppPicker value={gasApp} onChange={setGasApp} />
            <StagePicker value={gasStage} onChange={setGasStage} />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleRunGas} disabled={gas.status === 'running'}>
              {gas.status === 'running' ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Run {gasStage} agent
            </Button>

            <Button
              variant="destructive"
              onClick={handleInterrupt}
              disabled={gas.status !== 'running'}
            >
              <Hand className="mr-2 h-4 w-4" />
              Interrupt
            </Button>

            <Button
              variant="outline"
              onClick={handleRecover}
              disabled={
                recoverLoading ||
                (gas.status !== 'interrupted' && gas.status !== 'error' && gas.status !== 'done')
              }
            >
              {recoverLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              Recover session
            </Button>
          </div>

          {gasErr ? <p className="text-sm text-destructive">{gasErr}</p> : null}
          <LogPanel logs={gas.logs} />

          {recoverResult ? (
            <div className="space-y-2">
              <p className="text-sm font-semibold">Reconstructed context</p>
              <pre
                className="overflow-auto rounded-lg border border-border/60 bg-muted/30 p-3 text-xs leading-relaxed"
                style={{ maxHeight: '20rem' }}
              >
                {JSON.stringify(recoverResult, null, 2)}
              </pre>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
