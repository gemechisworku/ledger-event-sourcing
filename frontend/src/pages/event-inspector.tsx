import { useQuery } from '@tanstack/react-query'
import { Database, Layers, Loader2, Search } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { browseStream, findUpcastableEvent, listApplications, upcastCompare } from '@/lib/api'

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

type StreamEvent = {
  event_id: string
  event_type: string
  event_version: number
  stream_position: number
  global_position: number
  recorded_at: string | null
  payload: Record<string, unknown>
}

const PREFIXES = ['loan', 'credit', 'fraud', 'compliance', 'decision'] as const

export function EventInspectorPage() {
  const appsQ = useQuery({
    queryKey: ['applications-list'],
    queryFn: () => listApplications({ limit: 200 }),
    staleTime: 30_000,
  })
  const apps = (appsQ.data?.applications ?? []).filter((a) => a.state !== 'LOCAL')

  const streamOptions = useMemo(() => {
    const opts: { value: string; label: string }[] = []
    for (const app of apps) {
      for (const prefix of PREFIXES) {
        opts.push({
          value: `${prefix}-${app.application_id}`,
          label: `${prefix}-${app.application_id}`,
        })
      }
    }
    return opts
  }, [apps])

  // ── Stream browser ──
  const [streamId, setStreamId] = useState('')
  const [streamResult, setStreamResult] = useState<Record<string, unknown> | null>(null)
  const [streamLoading, setStreamLoading] = useState(false)
  const [streamErr, setStreamErr] = useState<string | null>(null)

  const handleBrowse = useCallback(async () => {
    if (!streamId.trim()) {
      setStreamErr('Enter a stream_id')
      return
    }
    setStreamLoading(true)
    setStreamErr(null)
    setStreamResult(null)
    try {
      setStreamResult(await browseStream(streamId.trim()))
    } catch (e) {
      setStreamErr((e as Error).message)
    } finally {
      setStreamLoading(false)
    }
  }, [streamId])

  const streamEvents = (streamResult as { events?: StreamEvent[] })?.events ?? []

  // ── Upcast comparison ──
  const [upcastId, setUpcastId] = useState('')
  const [upcastResult, setUpcastResult] = useState<Record<string, unknown> | null>(null)
  const [upcastLoading, setUpcastLoading] = useState(false)
  const [upcastErr, setUpcastErr] = useState<string | null>(null)

  const handleFindUpcastable = useCallback(async () => {
    setUpcastLoading(true)
    setUpcastErr(null)
    setUpcastResult(null)
    try {
      const r = await findUpcastableEvent()
      if ((r as { found?: boolean }).found && (r as { event_id?: string }).event_id) {
        const eid = (r as { event_id: string }).event_id
        setUpcastId(eid)
        setUpcastResult(await upcastCompare(eid))
      } else {
        setUpcastErr(
          (r as { hint?: string }).hint ?? 'No v1 events found. Run a pipeline first.',
        )
      }
    } catch (e) {
      setUpcastErr((e as Error).message)
    } finally {
      setUpcastLoading(false)
    }
  }, [])

  const handleUpcastCompare = useCallback(async () => {
    if (!upcastId.trim()) {
      setUpcastErr('Enter an event_id or click "Find v1 event"')
      return
    }
    setUpcastLoading(true)
    setUpcastErr(null)
    setUpcastResult(null)
    try {
      setUpcastResult(await upcastCompare(upcastId.trim()))
    } catch (e) {
      setUpcastErr((e as Error).message)
    } finally {
      setUpcastLoading(false)
    }
  }, [upcastId])

  const analysis = (upcastResult as { analysis?: Record<string, unknown> })?.analysis
  const rawEv = (upcastResult as { raw?: Record<string, unknown> })?.raw
  const upcastedEv = (upcastResult as { upcasted?: Record<string, unknown> })?.upcasted

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="flex items-start gap-3">
          <Database className="mt-1 h-8 w-8 shrink-0 text-primary" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-primary">
              Infrastructure
            </p>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Event Inspector</h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              Browse any event stream by stream_id, inspect individual events, and compare upcasted
              read-path results with the raw persisted payload to verify immutability.
            </p>
          </div>
        </div>
      </div>

      {/* ── Stream browser ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-primary" />
            <CardTitle>Browse stream</CardTitle>
          </div>
          <CardDescription>
            Pick a stream from the dropdown or type a custom stream_id. Streams follow the pattern{' '}
            <code className="text-xs">loan-APP_ID</code>,{' '}
            <code className="text-xs">credit-APP_ID</code>, etc.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Stream</Label>
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={streamOptions.some((o) => o.value === streamId) ? streamId : ''}
              onChange={(e) => {
                if (e.target.value) setStreamId(e.target.value)
              }}
            >
              <option value="">Select a known stream…</option>
              {PREFIXES.map((prefix) => (
                <optgroup key={prefix} label={prefix}>
                  {apps.map((a) => (
                    <option key={`${prefix}-${a.application_id}`} value={`${prefix}-${a.application_id}`}>
                      {prefix}-{a.application_id}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <Input
              value={streamId}
              onChange={(e) => setStreamId(e.target.value)}
              placeholder="Or type stream_id manually"
              className="flex-1"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleBrowse()
              }}
            />
            <Button onClick={handleBrowse} disabled={streamLoading}>
              {streamLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              Load
            </Button>
          </div>
          {streamErr ? <p className="text-sm text-destructive">{streamErr}</p> : null}
          {streamEvents.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                {(streamResult as { event_count?: number }).event_count} event(s) in{' '}
                <code className="text-xs">{streamId}</code>
              </p>
              <div className="divide-y divide-border/40 rounded-lg border border-border/60">
                {streamEvents.map((ev, idx) => (
                  <details key={idx} className="group">
                    <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-muted/40">
                      <Badge variant="outline" className="shrink-0 text-[10px]">
                        #{ev.stream_position}
                      </Badge>
                      <span className="font-medium">{ev.event_type}</span>
                      <Badge variant="secondary" className="text-[10px]">
                        v{ev.event_version}
                      </Badge>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {ev.recorded_at?.slice(0, 19) ?? '—'}
                      </span>
                      {ev.event_id ? (
                        <button
                          type="button"
                          className="text-[10px] text-primary underline"
                          onClick={(e) => {
                            e.stopPropagation()
                            setUpcastId(ev.event_id)
                          }}
                          title="Copy to upcast comparison"
                        >
                          inspect
                        </button>
                      ) : null}
                    </summary>
                    <div className="border-t border-border/30 bg-muted/20 px-3 py-2">
                      <JsonBlock value={ev.payload} maxH="16rem" />
                    </div>
                  </details>
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── Upcast vs raw ── */}
      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <CardTitle>Upcast vs raw comparison</CardTitle>
          </div>
          <CardDescription>
            Compare how the store delivers an event via the read path (with upcasters applied) vs the
            immutable payload persisted in the database. Fields added by upcasters are highlighted.
            The raw bytes on disk never change.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={handleFindUpcastable} disabled={upcastLoading}>
              Find v1 event automatically
            </Button>
          </div>
          <div className="flex gap-2">
            <Input
              value={upcastId}
              onChange={(e) => setUpcastId(e.target.value)}
              placeholder="event_id (UUID)"
              className="flex-1"
            />
            <Button onClick={handleUpcastCompare} disabled={upcastLoading}>
              {upcastLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Compare
            </Button>
          </div>
          {upcastErr ? <p className="text-sm text-destructive">{upcastErr}</p> : null}
          {analysis ? (
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
              <p>
                <strong>Stored version:</strong> v
                {String((analysis as Record<string, unknown>).stored_version)} →{' '}
                <strong>Read path version:</strong> v
                {String((analysis as Record<string, unknown>).read_path_version)}
              </p>
              {Array.isArray((analysis as Record<string, unknown>).fields_added_by_upcast) &&
              ((analysis as { fields_added_by_upcast: string[] }).fields_added_by_upcast).length >
                0 ? (
                <p className="mt-1">
                  <strong>Fields added by upcast:</strong>{' '}
                  {(
                    (analysis as { fields_added_by_upcast: string[] }).fields_added_by_upcast
                  ).map((f) => (
                    <Badge key={f} variant="secondary" className="mr-1 text-[10px]">
                      {f}
                    </Badge>
                  ))}
                </p>
              ) : null}
              <p className="mt-1 text-muted-foreground">
                Raw payload on disk is unchanged — upcasting runs only during the read path.
              </p>
            </div>
          ) : null}
          {rawEv && upcastedEv ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-1 text-sm font-semibold">
                  Raw persisted (v{String((rawEv as Record<string, unknown>).event_version)})
                </p>
                <JsonBlock value={rawEv} maxH="28rem" />
              </div>
              <div>
                <p className="mb-1 text-sm font-semibold">
                  Upcasted read path (v
                  {String((upcastedEv as Record<string, unknown>).event_version)})
                </p>
                <JsonBlock value={upcastedEv} maxH="28rem" />
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
