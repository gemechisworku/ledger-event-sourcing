import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { AlertCircle, Database, Sparkles } from 'lucide-react'

import { ApplicationListCard } from '@/components/applications/application-list-card'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { createApplication, listApplications, type ApplicationCreate, type ApplicationListItem } from '@/lib/api'
import { getAllPipelineRuns } from '@/lib/pipeline-history'
import { getRecentApplicationIds, pushRecentApplicationId } from '@/lib/recent-apps'
import { cn } from '@/lib/utils'

const LOAN_PURPOSES = [
  'working_capital',
  'equipment_financing',
  'real_estate',
  'expansion',
  'refinancing',
  'acquisition',
  'bridge',
] as const

const defaultForm: ApplicationCreate = {
  application_id: '',
  applicant_id: 'COMP-001',
  requested_amount_usd: '250000',
  loan_purpose: 'working_capital',
  loan_term_months: 36,
  submission_channel: 'web',
  contact_email: 'cfo@example.com',
  contact_name: 'Alex Kim',
  application_reference: '',
}

function localOnlyRow(applicationId: string): ApplicationListItem {
  return {
    application_id: applicationId,
    state: 'LOCAL',
    applicant_id: null,
    requested_amount_usd: null,
    decision: null,
    risk_tier: null,
    compliance_status: null,
    fraud_score: null,
    last_event_type: null,
    last_event_at: null,
    updated_at: null,
    stream_version: -1,
  }
}

export function ApplicationsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [recent, setRecent] = useState(() => getRecentApplicationIds())
  const [form, setForm] = useState<ApplicationCreate>(defaultForm)
  const [jumpId, setJumpId] = useState('')
  const [busy, setBusy] = useState(false)
  const [localRunsEpoch, setLocalRunsEpoch] = useState(0)

  useEffect(() => {
    const bump = () => setLocalRunsEpoch((n) => n + 1)
    const onVis = () => {
      if (document.visibilityState === 'visible') bump()
    }
    window.addEventListener('focus', bump)
    document.addEventListener('visibilitychange', onVis)
    return () => {
      window.removeEventListener('focus', bump)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  const listQ = useQuery({
    queryKey: ['applications'],
    queryFn: () => listApplications({ limit: 200 }),
    staleTime: 30_000,
  })

  const rows = useMemo(() => {
    const pipelineRuns = getAllPipelineRuns()
    const api = listQ.data?.applications ?? []
    const apiIds = new Set(api.map((a) => a.application_id))
    const extraIds = new Set<string>()
    for (const r of recent) extraIds.add(r)
    for (const k of Object.keys(pipelineRuns)) extraIds.add(k)
    const locals = [...extraIds].filter((id) => !apiIds.has(id)).map(localOnlyRow)
    return [...api, ...locals]
  }, [listQ.data?.applications, recent, localRunsEpoch])

  const pipelineRuns = getAllPipelineRuns()

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await createApplication(form)
      pushRecentApplicationId(form.application_id)
      setRecent(getRecentApplicationIds())
      qc.invalidateQueries({ queryKey: ['application', form.application_id] })
      qc.invalidateQueries({ queryKey: ['applications'] })
      toast.success('Application submitted')
      navigate(`/applications/${encodeURIComponent(form.application_id)}`)
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-10">
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2 text-primary">
              <Sparkles className="h-5 w-5" />
              <span className="text-xs font-semibold uppercase tracking-widest">Workbench</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-foreground">Applications</h1>
            <p className="mt-1 max-w-2xl text-muted-foreground">
              Browse applications from the ledger projection, local run history, and recent ids. Open any row for the
              command center.
            </p>
          </div>
          <Button asChild variant="secondary" className="shrink-0 shadow-sm">
            <Link to="/">Dashboard</Link>
          </Button>
        </div>
      </div>

      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">All applications</h2>
            <p className="text-sm text-muted-foreground">
              From <code className="rounded bg-muted px-1.5 py-0.5 text-xs">GET /v1/applications</code> plus browser-only
              rows.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={listQ.isFetching}
            onClick={() => void listQ.refetch()}
          >
            {listQ.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>

        {listQ.data?.note && (
          <div
            className={cn(
              'flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm',
              'text-amber-950 dark:text-amber-100',
            )}
          >
            <Database className="mt-0.5 h-5 w-5 shrink-0 text-amber-700 dark:text-amber-400" />
            <p>{listQ.data.note}</p>
          </div>
        )}

        {listQ.isLoading && <p className="text-muted-foreground">Loading applications…</p>}
        {listQ.isError && (
          <div className="flex items-start gap-3 rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
            <p>{(listQ.error as Error).message}</p>
          </div>
        )}

        {listQ.isSuccess && rows.length === 0 && !listQ.data?.note && (
          <p className="rounded-xl border border-dashed border-border bg-muted/30 px-4 py-8 text-center text-muted-foreground">
            No applications yet. Submit one below or open an id you already know.
          </p>
        )}

        {rows.length > 0 && (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-2">
            {rows.map((app) => {
              const runs = pipelineRuns[app.application_id] ?? []
              const localOnly = app.state === 'LOCAL'
              return (
                <ApplicationListCard key={app.application_id} app={app} runs={runs} localOnly={localOnly} />
              )
            })}
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
          <CardHeader>
            <CardTitle>Open by id</CardTitle>
            <CardDescription>Jump to the command center for a known application id.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Input
              className="max-w-xs"
              placeholder="e.g. MANUAL-001"
              value={jumpId}
              onChange={(e) => setJumpId(e.target.value)}
            />
            <Button
              type="button"
              variant="secondary"
              disabled={!jumpId.trim()}
              onClick={() => navigate(`/applications/${encodeURIComponent(jumpId.trim())}`)}
            >
              Open
            </Button>
          </CardContent>
        </Card>

        {recent.length > 0 && (
          <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
            <CardHeader>
              <CardTitle>Recent</CardTitle>
              <CardDescription>Stored in this browser (max 20).</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {recent.map((rid) => (
                <Button key={rid} variant="outline" size="sm" asChild className="rounded-full font-mono text-xs">
                  <Link to={`/applications/${encodeURIComponent(rid)}`}>{rid}</Link>
                </Button>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <CardTitle>New application</CardTitle>
          <CardDescription>
            Maps to <code className="text-xs">POST /v1/applications</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid max-w-xl gap-4">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="application_id">Application ID</Label>
                <Input
                  id="application_id"
                  required
                  value={form.application_id}
                  onChange={(e) => setForm((f) => ({ ...f, application_id: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="applicant_id">Applicant ID</Label>
                <Input
                  id="applicant_id"
                  required
                  value={form.applicant_id}
                  onChange={(e) => setForm((f) => ({ ...f, applicant_id: e.target.value }))}
                />
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="amt">Requested amount (USD)</Label>
                <Input
                  id="amt"
                  required
                  value={form.requested_amount_usd}
                  onChange={(e) => setForm((f) => ({ ...f, requested_amount_usd: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="term">Loan term (months)</Label>
                <Input
                  id="term"
                  type="number"
                  min={1}
                  max={600}
                  required
                  value={form.loan_term_months}
                  onChange={(e) => setForm((f) => ({ ...f, loan_term_months: Number(e.target.value) }))}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="purpose">Loan purpose</Label>
              <select
                id="purpose"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                value={form.loan_purpose}
                onChange={(e) => setForm((f) => ({ ...f, loan_purpose: e.target.value }))}
              >
                {LOAN_PURPOSES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="email">Contact email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  value={form.contact_email}
                  onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="name">Contact name</Label>
                <Input
                  id="name"
                  required
                  value={form.contact_name}
                  onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ref">Application reference</Label>
              <Input
                id="ref"
                value={form.application_reference}
                onChange={(e) => setForm((f) => ({ ...f, application_reference: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ch">Submission channel</Label>
              <Input
                id="ch"
                value={form.submission_channel}
                onChange={(e) => setForm((f) => ({ ...f, submission_channel: e.target.value }))}
              />
            </div>
            <Button type="submit" disabled={busy} className="w-fit shadow-sm">
              {busy ? 'Submitting…' : 'Submit application'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
