import { useVirtualizer } from '@tanstack/react-virtual'
import { useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PIPELINE_STAGES } from '@/lib/pipeline-stages'
import type { PipelineSseEvent } from '@/types/pipeline-sse'

const MAX_LINES = 50_000

type Row = {
  raw: PipelineSseEvent
}

function formatRow(r: Row): string {
  return JSON.stringify(r.raw)
}

type Props = {
  lines: PipelineSseEvent[]
  streamEnded: boolean
  onClear: () => void
}

export function JobLogPanel({ lines, streamEnded, onClear }: Props) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [filterType, setFilterType] = useState<string | 'all'>('all')
  const [filterStage, setFilterStage] = useState<string | 'all'>('all')
  const [search, setSearch] = useState('')

  const rows: Row[] = useMemo(() => {
    const capped = lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines
    let out = capped.map((raw) => ({ raw }))
    if (filterType !== 'all') {
      out = out.filter((r) => r.raw.type === filterType)
    }
    if (filterStage !== 'all') {
      out = out.filter((r) => 'stage' in r.raw && r.raw.stage === filterStage)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      out = out.filter((r) => formatRow(r).toLowerCase().includes(q))
    }
    return out
  }, [lines, filterType, filterStage, search])

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
    overscan: 12,
  })

  const vRows = virtualizer.getVirtualItems()

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">
          {lines.length} events
          {streamEnded ? ' · stream ended' : ''}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={onClear}>
          Clear
        </Button>
        <Input
          className="h-8 max-w-xs"
          placeholder="Search JSON…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="h-8 rounded-md border border-input bg-background px-2 text-sm"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as typeof filterType)}
        >
          <option value="all">All types</option>
          <option value="progress">progress</option>
          <option value="complete">complete</option>
          <option value="error">error</option>
        </select>
        <select
          className="h-8 rounded-md border border-input bg-background px-2 text-sm"
          value={filterStage}
          onChange={(e) => setFilterStage(e.target.value)}
        >
          <option value="all">All stages</option>
          {PIPELINE_STAGES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div
        ref={parentRef}
        className="h-[320px] overflow-auto rounded-md border border-border bg-muted/30 font-mono text-xs"
        role="log"
        aria-live="polite"
      >
        <div
          style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}
        >
          {vRows.map((vr) => {
            const row = rows[vr.index]
            const ty = row.raw.type
            return (
              <div
                key={vr.key}
                className="absolute left-0 top-0 flex w-full items-start gap-2 border-b border-border/50 px-2 py-1"
                style={{ transform: `translateY(${vr.start}px)` }}
              >
                <Badge
                  variant={
                    ty === 'error'
                      ? 'destructive'
                      : ty === 'complete'
                        ? 'success'
                        : 'secondary'
                  }
                  className="shrink-0"
                >
                  {ty}
                </Badge>
                <span className="break-all text-foreground">{formatRow(row)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
