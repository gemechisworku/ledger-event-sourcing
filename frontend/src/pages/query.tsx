import { Bot, Clock, Loader2, Search, Send, Sparkles, User } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useSearchParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import { queryNaturalLanguage } from '@/lib/api'
import type { ConversationMessage, NLQueryResponse } from '@/lib/api'
import { normalizeMarkdownTables } from '@/lib/normalizeMarkdownTables'

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  model?: string | null
  tokens?: number | null
  loading?: boolean
}

const EXAMPLE_QUERIES = [
  'Show me the complete decision history of application APEX-0001',
  'What is the current status of all applications?',
  'Verify the cryptographic integrity of APEX-0001',
  'What compliance checks were performed on APEX-0001?',
  'Show the compliance state of APEX-0001 as it existed at 2026-03-25T12:00:00',
  'List all applications with their risk tiers and decisions',
]

const remarkPlugins = [remarkGfm]

const mdComponents: Components = {
  table: ({ children, ...props }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border/60">
      <table className="min-w-full text-sm" {...props}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="bg-muted/50 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground" {...props}>
      {children}
    </thead>
  ),
  th: ({ children, ...props }) => (
    <th className="whitespace-nowrap px-3 py-2 font-semibold" {...props}>
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td className="border-t border-border/40 px-3 py-2" {...props}>
      {children}
    </td>
  ),
  tr: ({ children, ...props }) => (
    <tr className="even:bg-muted/20" {...props}>
      {children}
    </tr>
  ),
}

export function QueryPage() {
  const [searchParams] = useSearchParams()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const prefill = searchParams.get('q')
  useEffect(() => {
    if (prefill && messages.length === 0) {
      setInput('')
      void handleSubmit(prefill)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill])

  const handleSubmit = useCallback(
    async (overrideQuery?: string) => {
      const q = (overrideQuery ?? input).trim()
      if (!q) return
      if (!overrideQuery) setInput('')

      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: q,
        timestamp: Date.now(),
      }
      const loadingMsg: Message = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        loading: true,
      }

      const currentMessages = [...messages, userMsg]
      setMessages([...currentMessages, loadingMsg])

      const history: ConversationMessage[] = currentMessages
        .filter((m) => !m.loading && m.content)
        .map((m) => ({ role: m.role, content: m.content }))

      try {
        const res: NLQueryResponse = await queryNaturalLanguage(q, history.slice(0, -1))
        setMessages((prev) =>
          prev.map((m) =>
            m.id === loadingMsg.id
              ? {
                  ...m,
                  content: res.answer,
                  model: res.model,
                  tokens: res.tokens_used,
                  loading: false,
                }
              : m,
          ),
        )
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === loadingMsg.id
              ? {
                  ...m,
                  content: `Error: ${(err as Error).message}`,
                  loading: false,
                }
              : m,
          ),
        )
      }
    },
    [input, messages],
  )

  const isLoading = messages.some((m) => m.loading)

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="shrink-0 border-b border-border/60 bg-gradient-to-r from-primary/5 via-transparent to-transparent px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">Ask the Ledger</h1>
            <p className="text-sm text-muted-foreground">
              Query applications, decisions, compliance, and integrity using natural language
            </p>
          </div>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 md:px-6">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-2xl space-y-8 pt-8">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Bot className="h-8 w-8" />
              </div>
              <h2 className="text-lg font-semibold">What would you like to know?</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Ask about any application, decision, compliance check, or integrity verification
              </p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {EXAMPLE_QUERIES.map((eq) => (
                <button
                  key={eq}
                  onClick={() => void handleSubmit(eq)}
                  disabled={isLoading}
                  className="rounded-xl border border-border/80 bg-card/80 px-4 py-3 text-left text-sm text-foreground shadow-sm transition-all hover:border-primary/40 hover:bg-primary/5 hover:shadow-md disabled:opacity-50"
                >
                  {eq}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                {msg.role === 'assistant' && (
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Bot className="h-4 w-4" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'border border-border/60 bg-card shadow-sm'
                  }`}
                >
                  {msg.loading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Thinking…</span>
                    </div>
                  ) : (
                    <>
                      {msg.role === 'assistant' ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:mt-4 prose-headings:mb-2 prose-headings:font-semibold prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-hr:my-3 prose-blockquote:my-2 prose-pre:my-2 prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-[13px] prose-code:before:content-none prose-code:after:content-none prose-table:my-0">
                          <ReactMarkdown remarkPlugins={remarkPlugins} components={mdComponents}>
                            {normalizeMarkdownTables(msg.content)}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <div className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</div>
                      )}
                      {msg.role === 'assistant' && (msg.model || msg.tokens) && (
                        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border/40 pt-2">
                          {msg.model && (
                            <Badge variant="outline" className="text-[10px]">
                              {msg.model}
                            </Badge>
                          )}
                          {msg.tokens != null && (
                            <span className="text-[10px] text-muted-foreground">
                              {msg.tokens} tokens
                            </span>
                          )}
                          <span className="text-[10px] text-muted-foreground">
                            <Clock className="mr-0.5 inline h-3 w-3" />
                            {new Date(msg.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      )}
                    </>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-border/60 bg-background/95 px-4 py-3 backdrop-blur md:px-6">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void handleSubmit()
          }}
          className="mx-auto flex max-w-3xl gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about applications, decisions, compliance…"
              disabled={isLoading}
              className="w-full rounded-xl border border-border/80 bg-background py-2.5 pl-10 pr-4 text-sm shadow-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-60"
            />
          </div>
          <Button type="submit" disabled={isLoading || !input.trim()} size="icon" className="h-10 w-10 shrink-0 rounded-xl shadow-sm">
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </form>
        <p className="mx-auto mt-1.5 max-w-3xl text-center text-[11px] text-muted-foreground">
          Powered by OpenRouter LLM with function calling over the event store
        </p>
      </div>
    </div>
  )
}
