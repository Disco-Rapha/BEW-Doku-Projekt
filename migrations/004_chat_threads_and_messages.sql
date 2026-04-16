-- Migration 004: Chat-Threads und Chat-Messages für den Foundry-Agent
--
-- Kontext: Der neue Agent läuft über Microsoft Foundry Agent Service.
-- Foundry hält die Conversation-History serverseitig pro Thread, wir
-- spiegeln sie lokal für Datasette-Inspektion, UI-Rendering und Offline-Analyse.
--
-- Neue Tabellen:
--   chat_threads   — ein Thread pro Chat-Tab im UI. foundry_thread_id verbindet
--                    einen lokalen Thread mit einem Foundry-Thread.
--                    Nullable bis zur ersten Agent-Antwort (wird erst dann angelegt).
--   chat_messages  — lokaler Mirror aller Nachrichten (user/assistant/tool/system).
--                    Enthält Tool-Calls und -Ergebnisse als JSON für die UI.
--
-- Wichtig:
--   - foundry_thread_id UNIQUE erlaubt NULLs (SQLite-Verhalten: mehrere NULLs ok).
--   - ON DELETE CASCADE: wenn ein Thread gelöscht wird, fliegen seine Messages mit.
--   - project_id optional: ein Thread kann projekt-scoped sein oder global.

BEGIN;

-- ----------------------------------------------------------------
-- 1. chat_threads — Chat-Tabs im UI
-- ----------------------------------------------------------------
CREATE TABLE chat_threads (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT NOT NULL DEFAULT 'Neuer Chat',
    foundry_thread_id  TEXT,                    -- NULL bis zur ersten Foundry-Antwort
    project_id         INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    model_used         TEXT NOT NULL DEFAULT 'gpt-5.1',
    status             TEXT NOT NULL DEFAULT 'active',   -- active | archived
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_chat_threads_foundry
    ON chat_threads(foundry_thread_id)
    WHERE foundry_thread_id IS NOT NULL;

CREATE INDEX idx_chat_threads_project ON chat_threads(project_id);
CREATE INDEX idx_chat_threads_status  ON chat_threads(status);

-- ----------------------------------------------------------------
-- 2. chat_messages — lokaler Mirror der Foundry-Conversation
-- ----------------------------------------------------------------
-- role-Werte:
--   user       — Nachricht vom Benutzer
--   assistant  — Antwort vom Agent (Text + optionale Tool-Calls)
--   tool       — Ergebnis eines Custom-Function-Aufrufs
--   system     — interne System-Prompts (meist nicht in UI sichtbar)
CREATE TABLE chat_messages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id          INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role               TEXT NOT NULL,
    content            TEXT,                    -- darf NULL sein wenn nur Tool-Calls
    tool_calls_json    TEXT,                    -- JSON-Array bei assistant-Nachrichten
    tool_results_json  TEXT,                    -- JSON bei role='tool'
    foundry_message_id TEXT,                    -- ID aus Foundry für Rückverfolgung
    tokens_input       INTEGER,                 -- optional, aus Foundry-Usage
    tokens_output      INTEGER,                 -- optional
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_chat_messages_thread   ON chat_messages(thread_id);
CREATE INDEX idx_chat_messages_created  ON chat_messages(thread_id, created_at);

COMMIT;
