import { useEffect, useRef } from 'react'

import { getApiBase } from '@/lib/api-base'
import type { PipelineSseEvent } from '@/types/pipeline-sse'

type Options = {
  onEvent: (e: PipelineSseEvent) => void
  onDone?: () => void
  onError?: () => void
}

/**
 * Subscribes to BFF SSE for a pipeline job. Closes when `complete` or `error` is received.
 */
export function useJobStream(jobId: string | null, { onEvent, onDone, onError }: Options) {
  const cb = useRef({ onEvent, onDone, onError })
  cb.current = { onEvent, onDone, onError }

  useEffect(() => {
    if (!jobId) return

    const url = `${getApiBase()}/v1/jobs/${encodeURIComponent(jobId)}/stream`
    const es = new EventSource(url)

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as PipelineSseEvent
        cb.current.onEvent(data)
        if (data.type === 'complete' || data.type === 'error') {
          es.close()
          if (data.type === 'complete') cb.current.onDone?.()
          else cb.current.onError?.()
        }
      } catch {
        /* ignore malformed */
      }
    }

    es.onerror = () => {
      es.close()
      cb.current.onError?.()
    }

    return () => {
      es.close()
    }
  }, [jobId])
}
