import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, Layers, Loader2, Search, Sparkles } from 'lucide-react'
import { useCallback, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  browseStream,
  ensureUpcastDemo,
  findUpcastableEvent,
  listEventsCatalog,
  listStreams,
  upcastCompare,
} from '@/lib/api'

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

export function EventInspectorPage() {
  const queryClient = useQueryClient()

  const streamsQ = useQuery({
    queryKey: ['event-inspector-streams'],
    queryFn: () => listStreams({ limit: 2000 }),
    staleTime: 60_000,
  })

  const [v1CatalogOnly, setV1CatalogOnly] = useState(false)
  const catalogQ = useQuery({
    queryKey: ['event-inspector-catalog', v1CatalogOnly],
    queryFn: () =>
      listEventsCatalog({
        limit: 800,
        eventVersion: v1CatalogOnly ? 1 : undefined,
      }),
    staleTime: 30_000,
  })

  const [streamId, setStreamId] = useState('')
  const [streamResult, setStreamResult] = useState<Record<string, unknown> | null>(null)
  const [streamLoading, setStreamLoading] = useState(false)
  const [streamErr, setStreamErr] = useState<string | null>(null)

  const handleBrowse = useCallback(async () => {
    if (!streamId.trim()) {
      setStreamErr('Select or enter a stream_id')
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

  const [upcastId, setUpcastId] = useState('')
  const [upcastResult, setUpcastResult] = useState<Record<string, unknown> | null>(null)
  const [upcastLoading, setUpcastLoading] = useState(false)
  const [upcastErr, setUpcastErr] = useState<string | null>(null)
  const [demoBanner, setDemoBanner] = useState<string | null>(null)

  const handleEnsureDemo = useCallback(async () => {
    setUpcastLoading(true)
    setUpcastErr(null)
    setDemoBanner(null)
    try {
      const r = await ensureUpcastDemo()
      const parts: string[] = []
      if ((r as { created_credit?: boolean }).created_credit) parts.push('created credit v1 demo')
      if ((r as { created_decision?: boolean }).created_decision) parts.push('created decision v1 demo')
      setDemoBanner(
        parts.length > 0
          ? `Installed: ${parts.join('; ')}. Stream list refreshed.`
          : 'Demo v1 events already present. Stream list refreshed.',
      )
      await queryClient.invalidateQueries({ queryKey: ['event-inspector-catalog'] })
      await queryClient.invalidateQueries({ queryKey: ['event-inspector-streams'] })
    } catch (e) {
      setUpcastErr((e as Error).message)
    } finally {
      setUpcastLoading(false)
    }
  }, [queryClient])

  const compareByEventId = useCallback(async (eid: string) => {
    setUpcastLoading(true)
    setUpcastErr(null)
    setUpcastResult(null)
    setUpcastId(eid)
    try {
      setUpcastResult(await upcastCompare(eid))
    } catch (e) {
      setUpcastErr((e as Error).message)
    } finally {
      setUpcastLoading(false)
    }
  }, [])

  const handleCompareCreditDemo = useCallback(async () => {
    setUpcastLoading(true)
    setUpcastErr(null)
    try {
      const r = await ensureUpcastDemo()
      const id = (r as { credit_event_id?: string }).credit_event_id
      if (!id) throw new Error('No credit demo event id')
      await compareByEventId(id)
    } catch (e) {
      setUpcastErr((e as Error).message)
      setUpcastLoading(false)
    }
  }, [compareByEventId])

  const handleCompareDecisionDemo = useCallback(async () => {
    setUpcastLoading(true)
    setUpcastErr(null)
    try {
      const r = await ensureUpcastDemo()
      const id = (r as { decision_event_id?: string }).decision_event_id
      if (!id) throw new Error('No decision demo event id')
      await compareByEventId(id)
    } catch (e) {
      setUpcastErr((e as Error).message)
      setUpcastLoading(false)
    }
  }, [compareByEventId])

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
        setUpcastErr((r as { hint?: string }).hint ?? 'No events in the store.')
      }
    } catch (e) {
      setUpcastErr((e as Error).message)
    } finally {
      setUpcastLoading(false)
    }
  }, [])

  const handleUpcastCompare = useCallback(async () => {
    if (!upcastId.trim()) {
      setUpcastErr('Select an event_id from the list or enter a UUID')
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
  const explain = (upcastResult as { explain?: Record<string, string> })?.explain
  const rawEv = (upcastResult as { raw?: Record<string, unknown> })?.raw
  const upcastedEv = (upcastResult as { upcasted?: Record<string, unknown> })?.upcasted

  const streamRows = streamsQ.data?.streams ?? []
  const catalogEvents = catalogQ.data?.events ?? []

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
              Browse streams and events loaded from the database. Compare upcasted read-path rows
              with raw persisted payloads &mdash; use v1 events for demos where upcasters apply.
            </p>
          </div>
        </div>
      </div>

      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-primary" />
            <CardTitle>Browse stream</CardTitle>
          </div>
          <CardDescription>
            Choose a stream that exists in the event store ({streamsQ.data?.total ?? '\u2026'} distinct
            streams). Or type a custom <code className="text-xs">stream_id</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Stream</Label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <select
                className="h-9 w-full min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={streamRows.some((s) => s.stream_id === streamId) ? streamId : ''}
                onChange={(e) => {
                  const v = e.target.value
                  if (v) setStreamId(v)
                }}
              >
                <option value="">Select a stream from the database&hellip;</option>
                {streamRows.map((s) => (
                  <option key={s.stream_id} value={s.stream_id}>
                    {s.stream_id} ({s.event_count} events)
                  </option>
                ))}
              </select>
              {streamsQ.isFetching ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
              ) : null}
            </div>
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
          {streamsQ.isError ? (
            <p className="text-sm text-destructive">Could not load stream list (PostgreSQL API required).</p>
          ) : null}
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
                        {ev.recorded_at?.slice(0, 19) ?? '\u2014'}
                      </span>
                      {ev.event_id ? (
                        <button
                          type="button"
                          className="text-[10px] text-primary underline"
                          onClick={(e) => {
                            e.stopPropagation()
                            setUpcastId(ev.event_id)
                          }}
                          title="Use in upcast comparison"
                        >
                          use for upcast
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

      <Card className="border-0 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <CardTitle>Upcast vs raw comparison</CardTitle>
          </div>
          <CardDescription>
            <strong>Upcasting</strong> is schema evolution on read: older payloads stay in the database as written;
            the read path maps them to the current shape in memory. Use <strong>Prepare demo v1 events</strong> then{' '}
            <strong>Compare credit</strong> or <strong>Compare decision</strong> to see v1 (persisted) vs v2 (display)
            side by side.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-primary/25 bg-primary/5 px-4 py-3 text-sm leading-relaxed">
            <p className="font-semibold text-foreground">How to demo</p>
            <p className="mt-1 text-muted-foreground">
              Run <strong>Prepare demo v1 events</strong> once (idempotent). Then open <strong>Compare credit</strong> &mdash;
              left column is the immutable row in Postgres, right column is what the app sees after upcasters on load.
              Nothing rewrites the stored row.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="default" onClick={handleEnsureDemo} disabled={upcastLoading}>
              {upcastLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
              Prepare demo v1 events
            </Button>
            <Button variant="secondary" onClick={handleCompareCreditDemo} disabled={upcastLoading}>
              Compare credit (v1&rarr;v2)
            </Button>
            <Button variant="secondary" onClick={handleCompareDecisionDemo} disabled={upcastLoading}>
              Compare decision (v1&rarr;v2)
            </Button>
            <Button variant="outline" onClick={handleFindUpcastable} disabled={upcastLoading}>
              Auto-pick (prefers demo v1)
            </Button>
          </div>
          {demoBanner ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-400">{demoBanner}</p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={v1CatalogOnly}
                onChange={(e) => setV1CatalogOnly(e.target.checked)}
                className="rounded border-input"
              />
              Event list: v1 only ({catalogQ.data?.total ?? '\u2026'} matches)
            </label>
            {catalogQ.isFetching ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : null}
          </div>

          <div className="space-y-1">
            <Label>Event</Label>
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={catalogEvents.some((e) => e.event_id === upcastId) ? upcastId : ''}
              onChange={(e) => {
                const v = e.target.value
                if (v) setUpcastId(v)
              }}
            >
              <option value="">Select an event_id from the database&hellip;</option>
              {catalogEvents.map((ev) => (
                <option key={ev.event_id} value={ev.event_id}>
                  {ev.event_type} v{ev.event_version} &middot; {ev.stream_id} #{ev.stream_position} &middot;{' '}
                  {ev.event_id.slice(0, 8)}&hellip;
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-2">
            <Input
              value={upcastId}
              onChange={(e) => setUpcastId(e.target.value)}
              placeholder="event_id (UUID)"
              className="flex-1 font-mono text-xs"
            />
            <Button onClick={handleUpcastCompare} disabled={upcastLoading}>
              {upcastLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Compare
            </Button>
          </div>

          {catalogQ.isError ? (
            <p className="text-sm text-destructive">Could not load event catalog.</p>
          ) : null}
          {v1CatalogOnly && catalogEvents.length === 0 && !catalogQ.isFetching ? (
            <p className="text-sm text-muted-foreground">
              No v1 events in this database &mdash; uncheck &quot;v1 only&quot; or seed v1 rows. You can still compare any
              event; raw vs read path may match when stored as v2.
            </p>
          ) : null}
          {upcastErr ? <p className="text-sm text-destructive">{upcastErr}</p> : null}
          {analysis ? (
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
              <p>
                <strong>Stored version:</strong> v{String((analysis as Record<string, unknown>).stored_version)} &rarr;{' '}
                <strong>Read path version:</strong> v{String((analysis as Record<string, unknown>).read_path_version)}
              </p>
              {Array.isArray((analysis as Record<string, unknown>).fields_added_by_upcast) &&
              ((analysis as { fields_added_by_upcast: string[] }).fields_added_by_upcast).length > 0 ? (
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
                Raw payload on disk is unchanged &mdash; upcasting runs only during the read path.
              </p>
            </div>
          ) : null}
          {explain && (analysis as Record<string, unknown>)?.version_changed_by_upcast ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm">
              <p className="font-semibold text-amber-700 dark:text-amber-400">
                What you are seeing
              </p>
              <p className="mt-1 text-muted-foreground">
                <strong>Left (v{String((analysis as Record<string, unknown>).stored_version)}):</strong>{' '}
                {explain.persisted_in_database}
              </p>
              <p className="mt-1 text-muted-foreground">
                <strong>Right (v{String((analysis as Record<string, unknown>).read_path_version)}):</strong>{' '}
                {explain.read_path_display_only}
              </p>
            </div>
          ) : null}
          {explain && !(analysis as Record<string, unknown>)?.version_changed_by_upcast ? (
            <div className="rounded-lg border border-zinc-500/30 bg-zinc-500/5 px-4 py-3 text-sm text-muted-foreground">
              {explain.when_identical}
            </div>
          ) : null}
          {rawEv && upcastedEv ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-1 text-sm font-semibold text-red-600 dark:text-red-400">
                  Database row &mdash; v{String((rawEv as Record<string, unknown>).event_version)} (immutable, never rewritten)
                </p>
                <JsonBlock value={(rawEv as Record<string, unknown>).payload} maxH="28rem" />
              </div>
              <div>
                <p className="mb-1 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                  Read path &mdash; v{String((upcastedEv as Record<string, unknown>).event_version)} (upcasted in memory for display)
                </p>
                <JsonBlock value={(upcastedEv as Record<string, unknown>).payload} maxH="28rem" />
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
