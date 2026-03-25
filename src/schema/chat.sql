-- Natural-language chat persistence (PostgreSQL)
-- Scoped by client_session_id (browser UUID) — not a substitute for auth.

CREATE TABLE IF NOT EXISTS nl_conversations (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_session_id  TEXT NOT NULL,
  title              TEXT NOT NULL DEFAULT 'New chat',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nl_conversations_session_updated
  ON nl_conversations (client_session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS nl_messages (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id    UUID NOT NULL REFERENCES nl_conversations (id) ON DELETE CASCADE,
  role               TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content            TEXT NOT NULL,
  model              TEXT,
  tokens_used        INTEGER,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nl_messages_conversation_created
  ON nl_messages (conversation_id, created_at);
