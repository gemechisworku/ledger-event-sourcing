import { useCallback, useEffect, useRef, useState } from 'react'

import { getApiBase } from '@/lib/api-base'

export type AgentSseEvent = {
  type: string
  label?: string
  message?: string
  stream_id?: string
  event_type?: string
  expected_version?: number
  actual_version?: number
  event_types?: string[]
  session_id?: string
  duration_ms?: number
  ok?: boolean
  error?: string
  application_id?: string
  stage?: string
  timestamp?: string
  [key: string]: unknown
}

type Status = 'idle' | 'running' | 'done' | 'error' | 'interrupted'

const TERMINAL_TYPES = new Set(['complete', 'error', 'interrupted'])

export function useAgentStream() {
  const [logs, setLogs] = useState<AgentSseEvent[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  const start = useCallback((jid: string) => {
    esRef.current?.close()
    setLogs([])
    setJobId(jid)
    setStatus('running')

    const url = `${getApiBase()}/v1/jobs/${encodeURIComponent(jid)}/stream`
    const es = new EventSource(url)
    esRef.current = es

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as AgentSseEvent
        setLogs((prev) => [...prev, data])
        if (TERMINAL_TYPES.has(data.type)) {
          es.close()
          esRef.current = null
          if (data.type === 'complete') setStatus('done')
          else if (data.type === 'interrupted') setStatus('interrupted')
          else setStatus('error')
        }
      } catch {
        /* malformed */
      }
    }

    es.onerror = () => {
      es.close()
      esRef.current = null
      setStatus((prev) => (prev === 'running' ? 'error' : prev))
    }
  }, [])

  const reset = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setLogs([])
    setStatus('idle')
    setJobId(null)
  }, [])

  useEffect(() => {
    return () => {
      esRef.current?.close()
    }
  }, [])

  return { logs, status, jobId, start, reset }
}
