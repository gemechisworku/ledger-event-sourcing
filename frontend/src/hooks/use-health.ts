import { useQuery } from '@tanstack/react-query'

import { getHealth } from '@/lib/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: 2,
  })
}
