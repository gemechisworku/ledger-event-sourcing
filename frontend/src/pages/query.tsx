import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Clock, Loader2, MessageSquare, MessageSquarePlus, Search, Send, Sparkles, Trash2, User } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useSearchParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  queryNaturalLanguageInConversation,
  type NLQueryResponse,
} from '@/lib/api'
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

function mapRowsToMessages(
  rows: { id: string; role: string; content: string; model: string | null; tokens_used: number | null; created_at: string }[],
): Message[] {
  return rows.map((m) => ({
    id: m.id,
    role: m.role as 'user' | 'assistant',
    content: m.content,
    timestamp: new Date(m.created_at).getTime(),
    model: m.model,
    tokens: m.tokens_used,
  }))
}

export function QueryPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('c')

  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [persistenceError, setPersistenceError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const prefillDone = useRef(false)
  const isStreamingRef = useRef(false)

  const listQ = useQuery({
    queryKey: ['nl-conversations'],
    queryFn: listConversations,
    retry: false,
  })

  const detailQ = useQuery({
    queryKey: ['nl-conversation', conversationId],
    queryFn: () => getConversation(conversationId!),
    enabled: !!conversationId,
  })

  useEffect(() => {
    if (listQ.error) {
      setPersistenceError((listQ.error as Error).message)
    } else {
      setPersistenceError(null)
    }
  }, [listQ.error])

  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      return
    }
    if (detailQ.data?.messages && !isStreamingRef.current) {
      setMessages(mapRowsToMessages(detailQ.data.messages))
    }
  }, [conversationId, detailQ.data])

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const runQueryForConversation = useCallback(
    async (cid: string, q: string) => {
      isStreamingRef.current = true
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
      setMessages((prev) => [...prev, userMsg, loadingMsg])

      try {
        const res: NLQueryResponse = await queryNaturalLanguageInConversation(cid, q)
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
        await queryClient.invalidateQueries({ queryKey: ['nl-conversations'] })
        await queryClient.invalidateQueries({ queryKey: ['nl-conversation', cid] })
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
      } finally {
        isStreamingRef.current = false
      }
    },
    [queryClient],
  )

  const handleSubmit = useCallback(
    async (overrideQuery?: string) => {
      const q = (overrideQuery ?? input).trim()
      if (!q) return
      if (!overrideQuery) setInput('')

      let cid = conversationId
      if (!cid) {
        try {
          const conv = await createConversation()
          cid = conv.id
          setSearchParams({ c: cid }, { replace: false })
        } catch (e) {
          setMessages((prev) => [
            ...prev,
            {
              id: `e-${Date.now()}`,
              role: 'assistant',
              content: `Error: ${(e as Error).message}`,
              timestamp: Date.now(),
            },
          ])
          return
        }
      }
      await runQueryForConversation(cid, q)
    },
    [input, conversationId, runQueryForConversation, setSearchParams],
  )

  const prefillQ = searchParams.get('q')
  const prefillC = searchParams.get('c')
  useEffect(() => {
    if (!prefillQ || prefillDone.current) return
    prefillDone.current = true
    setInput('')
    void (async () => {
      try {
        let cid = prefillC
        if (!cid) {
          const conv = await createConversation()
          cid = conv.id
        }
        setSearchParams({ c: cid! }, { replace: true })
        await runQueryForConversation(cid!, prefillQ)
      } catch {
        prefillDone.current = false
      }
    })()
  }, [prefillQ, prefillC, runQueryForConversation, setSearchParams])

  const startNewChat = useCallback(() => {
    prefillDone.current = false
    setSearchParams({}, { replace: false })
    setMessages([])
    setInput('')
    inputRef.current?.focus()
  }, [setSearchParams])

  const selectConversation = useCallback(
    (id: string) => {
      prefillDone.current = true
      setSearchParams({ c: id })
    },
    [setSearchParams],
  )

  const removeConversation = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation()
      if (!confirm('Delete this conversation and all its messages?')) return
      try {
        await deleteConversation(id)
        await queryClient.invalidateQueries({ queryKey: ['nl-conversations'] })
        if (conversationId === id) {
          startNewChat()
        }
      } catch (err) {
        alert((err as Error).message)
      }
    },
    [conversationId, queryClient, startNewChat],
  )

  const isLoading = messages.some((m) => m.loading)
  const conversations = listQ.data?.conversations ?? []

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <aside className="flex w-72 shrink-0 flex-col border-r border-border/60 bg-sidebar/40 backdrop-blur">
        <div className="flex items-center justify-between gap-2 border-b border-border/40 p-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Chats</span>
          <Button variant="outline" size="sm" className="h-8 gap-1 rounded-lg text-xs" onClick={() => void startNewChat()}>
            <MessageSquarePlus className="h-3.5 w-3.5" />
            New
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {listQ.isLoading && <p className="px-2 py-3 text-xs text-muted-foreground">Loading…</p>}
          {persistenceError && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-2 py-2 text-[11px] text-destructive">
              {persistenceError}
            </p>
          )}
          {!listQ.isLoading &&
            !persistenceError &&
            conversations.map((c) => (
              <div
                key={c.id}
                role="button"
                tabIndex={0}
                onClick={() => selectConversation(c.id)}
                onKeyDown={(e) => e.key === 'Enter' && selectConversation(c.id)}
                className={`group mb-1 flex cursor-pointer items-start gap-2 rounded-xl px-2 py-2 text-left text-sm transition-colors hover:bg-primary/5 ${
                  conversationId === c.id ? 'bg-primary/10 ring-1 ring-primary/20' : ''
                }`}
              >
                <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium leading-tight">{c.title}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {c.message_count} msg · {new Date(c.updated_at).toLocaleString()}
                  </div>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-md p-1 text-muted-foreground opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                  aria-label="Delete conversation"
                  onClick={(e) => void removeConversation(c.id, e)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          {!listQ.isLoading && !persistenceError && conversations.length === 0 && (
            <p className="px-2 py-4 text-xs text-muted-foreground">No saved chats yet. Send a message to start.</p>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
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
                    disabled={isLoading || !!persistenceError}
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
                              <span className="text-[10px] text-muted-foreground">{msg.tokens} tokens</span>
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
                disabled={isLoading || !!persistenceError}
                className="w-full rounded-xl border border-border/80 bg-background py-2.5 pl-10 pr-4 text-sm shadow-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-60"
              />
            </div>
            <Button
              type="submit"
              disabled={isLoading || !input.trim() || !!persistenceError}
              size="icon"
              className="h-10 w-10 shrink-0 rounded-xl shadow-sm"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
          <p className="mx-auto mt-1.5 max-w-3xl text-center text-[11px] text-muted-foreground">
            Conversations are saved per browser session. Powered by OpenRouter LLM with function calling over the event
            store.
          </p>
        </div>
      </div>
    </div>
  )
}
