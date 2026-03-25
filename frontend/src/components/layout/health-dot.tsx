import { useHealth } from '@/hooks/use-health'
import { cn } from '@/lib/utils'

export function HealthDot() {
  const q = useHealth()
  const ok = q.isSuccess && q.data?.status === 'ok'
  const warn = q.isSuccess && q.data?.database !== 'ok' && q.data?.database !== 'in-memory'
  return (
    <span className="flex items-center gap-2 text-sm text-muted-foreground">
      <span
        className={cn(
          'flex h-2.5 w-2.5 rounded-full',
          q.isLoading && 'bg-muted-foreground',
          q.isError && 'bg-destructive',
          ok && !warn && 'bg-emerald-500',
          ok && warn && 'bg-amber-500',
        )}
        title={
          q.isError
            ? 'API unreachable'
            : q.data
              ? `${q.data.database} · pool=${q.data.store_pool}`
              : '…'
        }
      />
      {q.isError ? 'API offline' : q.data ? `API · ${q.data.database}` : '…'}
    </span>
  )
}
