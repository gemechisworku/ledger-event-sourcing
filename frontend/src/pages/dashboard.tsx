import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Search, Sparkles } from 'lucide-react'
import { useCallback, useState } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getHealth, queryNaturalLanguage } from '@/lib/api'
import type { NLQueryResponse } from '@/lib/api'
import { normalizeMarkdownTables } from '@/lib/normalizeMarkdownTables'

const remarkPlugins = [remarkGfm]

const mdComponents: Components = {
  table: ({ children, ...props }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border/60">
      <table className="min-w-full text-sm" {...props}>{children}</table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="bg-muted/50 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground" {...props}>{children}</thead>
  ),
  th: ({ children, ...props }) => <th className="whitespace-nowrap px-3 py-2 font-semibold" {...props}>{children}</th>,
  td: ({ children, ...props }) => <td className="border-t border-border/40 px-3 py-2" {...props}>{children}</td>,
  tr: ({ children, ...props }) => <tr className="even:bg-muted/20" {...props}>{children}</tr>,
}

export function DashboardPage() {
  const q = useQuery({ queryKey: ['health'], queryFn: getHealth })

  const [nlQuery, setNlQuery] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlResult, setNlResult] = useState<NLQueryResponse | null>(null)
  const [nlError, setNlError] = useState<string | null>(null)

  const handleNlQuery = useCallback(async () => {
    if (!nlQuery.trim()) return
    setNlLoading(true)
    setNlError(null)
    setNlResult(null)
    try {
      const res = await queryNaturalLanguage(nlQuery.trim())
      setNlResult(res)
    } catch (err) {
      setNlError((err as Error).message)
    } finally {
      setNlLoading(false)
    }
  }, [nlQuery])

  return (
    <div className="space-y-8">
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-card to-muted/30 p-6 shadow-sm ring-1 ring-border/40 md:p-8">
        <div className="pointer-events-none absolute -left-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2 text-primary">
              <Activity className="h-5 w-5" />
              <span className="text-xs font-semibold uppercase tracking-widest">Overview</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
            <p className="mt-1 max-w-xl text-muted-foreground">
              Operational view of the Ledger BFF and quick entry points.
            </p>
          </div>
          <Button asChild className="shadow-sm">
            <Link to="/applications" className="gap-2">
              Applications
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </div>

      <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <CardTitle>Ask the Ledger</CardTitle>
          </div>
          <CardDescription>
            Query application data using natural language. Try: &quot;Show me the complete decision history of application APEX-0001&quot;
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void handleNlQuery()
            }}
            className="flex gap-2"
          >
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={nlQuery}
                onChange={(e) => setNlQuery(e.target.value)}
                placeholder="Ask about applications, decisions, compliance..."
                className="w-full rounded-xl border border-border/80 bg-background py-2.5 pl-10 pr-4 text-sm shadow-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <Button type="submit" disabled={nlLoading || !nlQuery.trim()} className="shadow-sm">
              {nlLoading ? 'Thinking…' : 'Ask'}
            </Button>
          </form>
          <div className="flex items-center gap-2">
            <Link to="/query" className="text-xs text-primary hover:underline">
              Open full query console →
            </Link>
          </div>
          {nlError && <p className="text-sm text-destructive">{nlError}</p>}
          {nlResult && (
            <div className="space-y-2 rounded-xl border border-border/60 bg-muted/30 p-4">
              <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:mt-3 prose-headings:mb-1.5 prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-hr:my-2 prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-[13px] prose-code:before:content-none prose-code:after:content-none prose-table:my-0">
                <ReactMarkdown remarkPlugins={remarkPlugins} components={mdComponents}>
                  {normalizeMarkdownTables(nlResult.answer)}
                </ReactMarkdown>
              </div>
              {nlResult.model && (
                <p className="text-xs text-muted-foreground">
                  Model: {nlResult.model} · Tokens: {nlResult.tokens_used ?? '—'}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
          <CardHeader>
            <CardTitle>Event store</CardTitle>
            <CardDescription>
              From <code className="text-xs">GET /health</code>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {q.isLoading && <p className="text-muted-foreground">Loading…</p>}
            {q.isError && <p className="text-destructive">{(q.error as Error).message}</p>}
            {q.data && (
              <>
                <p>
                  <span className="text-muted-foreground">Database:</span> {q.data.database}
                </p>
                <p>
                  <span className="text-muted-foreground">Store pool:</span>{' '}
                  {q.data.store_pool ? 'yes' : 'no'}
                </p>
              </>
            )}
          </CardContent>
        </Card>
        <Card className="border-0 bg-card/90 shadow-md ring-1 ring-border/60">
          <CardHeader>
            <CardTitle>Applications</CardTitle>
            <CardDescription>Browse ledger rows, run pipelines, and inspect streams.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button asChild variant="secondary" className="shadow-sm">
              <Link to="/applications">Open applications</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/applications">New application</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
