-- Sherman Bot - Supabase Schema
-- Run this in Supabase SQL Editor (https://supabase.com/dashboard)

-- Conversations (chat history)
CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_chat_id ON conversations(chat_id);

-- Message deduplication
CREATE TABLE IF NOT EXISTS seen_messages (
    message_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- FAQ
CREATE TABLE IF NOT EXISTS faq (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Courses
CREATE TABLE IF NOT EXISTS courses (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price TEXT NOT NULL,
    audience TEXT DEFAULT '',
    chapters TEXT DEFAULT '',
    purchase_url TEXT DEFAULT '',
    description TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Content sections (about, syllabus, contact, etc.)
CREATE TABLE IF NOT EXISTS content_sections (
    id BIGSERIAL PRIMARY KEY,
    section_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Behavioral rules
CREATE TABLE IF NOT EXISTS rules (
    id BIGSERIAL PRIMARY KEY,
    rule_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Disable RLS for backend service access
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE seen_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE faq ENABLE ROW LEVEL SECURITY;
ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "service_all" ON conversations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all" ON seen_messages FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all" ON faq FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all" ON courses FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all" ON content_sections FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all" ON rules FOR ALL USING (true) WITH CHECK (true);
