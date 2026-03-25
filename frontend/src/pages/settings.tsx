import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getApiBase, setApiBaseOverride } from '@/lib/api-base'

export function SettingsPage() {
  const [url, setUrl] = useState(getApiBase())

  useEffect(() => {
    setUrl(getApiBase())
  }, [])

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Override the Ledger API base URL (stored in localStorage). Reload the app after saving.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>API base URL</CardTitle>
          <CardDescription>
            Default comes from <code className="text-xs">VITE_API_BASE_URL</code> at build time (
            <code className="text-xs">http://127.0.0.1:8000</code>).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="api">Base URL</Label>
            <Input
              id="api"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://127.0.0.1:8000"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={() => {
                setApiBaseOverride(url.trim())
                toast.success('Saved. Reload the page to apply everywhere.')
              }}
            >
              Save
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setApiBaseOverride(null)
                setUrl(getApiBase())
                toast.message('Cleared override. Reload to use env default.')
              }}
            >
              Clear override
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Ensure FastAPI <code className="rounded bg-muted px-1">CORS_ORIGINS</code> includes your
            dev origin (e.g. <code className="rounded bg-muted px-1">http://localhost:5173</code>).
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
