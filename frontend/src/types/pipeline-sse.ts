export type PipelineSseEvent =
  | {
      type: 'progress'
      stage?: string
      message?: string
      index?: number
      total?: number
      pct?: number
      application_id?: string
    }
  | { type: 'complete'; application_id?: string }
  | { type: 'error'; message?: string; application_id?: string }

export type StageStatus = 'idle' | 'running' | 'completed' | 'failed'
