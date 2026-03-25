import { useQuery } from '@tanstack/react-query'
import { Clock, Loader2, Scale, Search } from 'lucide-react'
import { useCallback, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { complianceCompare, listApplications } from '@/lib/api'

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

type TimelineEntry = { event_type: string; stream_position: number; recorded_at: string | null }

export function ComplianceAuditPage() {
  const appsQ = useQuery({
    queryKey: ['applications-list'],
    queryFn: () => listApplications({ limit: 200 }),
    staleTime: 30_000,
  })
  const apps = (appsQ.data?.applications ?? []).filter((a) => a.state !== 'LOCAL')

  const [appId, setAppId] = useState('')
  const [asOf, setAsOf] = useState('')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const timeline = (result as { compliance_event_timeline?: TimelineEntry[] })
    ?.compliance_event_timeline

  const handleCompare = useCallback(async () => {
    if (!appId.trim()) { setErr('Select an application'); return }
    if (!asOf.trim()) { setErr('Enter or pick an as_of timestamp'); return }
    setLoading(true); setErr(null); setResult(null)
    try {
      setResult(await complianceCompare(appId.trim(), asOf.trim()))
    } catch (e) { setErr((e as Error).message) }
    finally { setLoading(false) }
  }, [appId, asOf])

  const handlePreload = useCallback(async () => {
    if (!appId.trim()) { setErr('Select an application first'); return }
    setLoading(true); setErr(null); setResult(null)
    try {
      const now = new Date().toISOString()
      setResult(await complianceCompare(appId.trim(), now))
    } catch (e) { setErr((e as Error).message) }
    finally { setLoading(false) }
  }, [appId])

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="flex items-start gap-3">
          <Scale className="mt-1 h-8 w-8 shrink-0 text-primary" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-primary">Regulatory</p>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Compliance Audit</h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              Query the compliance state of any application at a past point in time and compare it
              with the current state. The compliance projection replays the event stream up to the
              requested timestamp — no snapshots are mutated.
            </p>
          </div>
        </div>
      </div>

      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-primary" />
            <CardTitle>Temporal compliance query</CardTitle>
          </div>
          <CardDescription>
            Select an application that has been through the compliance stage, pick a timestamp
            (or click one from the event timeline), and compare.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Application</Label>
              <select
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={appId}
                onChange={(e) => { setAppId(e.target.value); setResult(null) }}
              >
                <option value="">Select…</option>
                {apps.map((a) => (
                  <option key={a.application_id} value={a.application_id}>
                    {a.application_id} — {a.compliance_status ?? a.state ?? '?'}
                  </option>
                ))}
              </select>
              <Input
                placeholder="Or type application_id"
                value={appId}
                onChange={(e) => setAppId(e.target.value)}
                className="mt-1"
              />
            </div>
            <div className="space-y-1">
              <Label>as_of (ISO-8601)</Label>
              <Input
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
                placeholder="2025-06-01T12:00:00Z"
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleCompare} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
              Compare compliance
            </Button>
            <Button variant="outline" onClick={handlePreload} disabled={loading}>
              Load timeline
            </Button>
          </div>

          {err ? <p className="text-sm text-destructive">{err}</p> : null}

          {timeline && timeline.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">
                Compliance event timeline — click a timestamp to set as_of before it
              </p>
              <div className="flex flex-wrap gap-1.5">
                {timeline.map((t, i) => (
                  <button
                    key={i}
                    type="button"
                    className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-muted/40 px-2 py-1 text-xs transition hover:bg-muted"
                    onClick={() => {
                      if (t.recorded_at) {
                        const d = new Date(t.recorded_at)
                        d.setMilliseconds(d.getMilliseconds() - 1)
                        setAsOf(d.toISOString())
                      }
                    }}
                    title={`Set as_of just before this event (${t.recorded_at})`}
                  >
                    <Badge variant="outline" className="text-[10px]">{t.stream_position}</Badge>
                    <span className="font-medium">{t.event_type}</span>
                    <span className="text-muted-foreground">{t.recorded_at?.slice(0, 19) ?? '—'}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {result ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-1 text-sm font-semibold">
                  Current compliance
                </p>
                <JsonBlock
                  value={(result as { current?: unknown }).current}
                  maxH="28rem"
                />
              </div>
              <div>
                <p className="mb-1 text-sm font-semibold">
                  As of {(result as { as_of?: string }).as_of ?? asOf}
                </p>
                <JsonBlock
                  value={(result as { as_of_projection?: unknown }).as_of_projection}
                  maxH="28rem"
                />
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
