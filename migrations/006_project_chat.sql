-- Migration 006: 1-Chat-pro-Projekt (Datenmodell-Rebuild)
--
-- Hintergrund: Bisher hatte jedes Projekt beliebig viele Chat-Threads,
-- jeder startete bei Null. Neues Modell: pro Projekt genau EIN persistenter
-- Chat, der tagelang laeuft. Vor der Kontext-Kompression schreibt Disco
-- strukturierte Memory-Files (.disco/memory/) und laedt sie danach zurueck.
-- Deshalb wird der Thread-Begriff komplett entfernt.
--
-- Aenderungen:
--   - DROP chat_messages (alte Form mit thread_id)
--   - DROP chat_threads
--   - CREATE project_chat_state  (eine Zeile pro Projekt)
--   - CREATE chat_messages      (neue Form mit project_slug + is_compacted)
--
-- Dev-Mode: Nutzer hat Datenverlust explizit ok'd ("löschen, starten neu").
-- Bestehende Foundry-Threads in Sweden Central bleiben unangetastet —
-- sie sind fuer Disco unsichtbar und koennen ignoriert werden.

BEGIN;

-- ----------------------------------------------------------------
-- 1. Alte Tabellen entfernen (inkl. ihrer Indizes via DROP TABLE)
-- ----------------------------------------------------------------
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_threads;

-- ----------------------------------------------------------------
-- 2. project_chat_state — eine Zeile pro Projekt
-- ----------------------------------------------------------------
-- Primaerschluessel ist der Projekt-Slug. Kein FK, weil projects.slug
-- nur via partiellem UNIQUE-Index eindeutig ist (Migration 005) —
-- damit laesst sich keine harte Referenzintegritaet erzwingen.
-- Stattdessen: Consistency ueber die App, CASCADE-Delete manuell.
CREATE TABLE project_chat_state (
    project_slug         TEXT PRIMARY KEY,
    foundry_response_id  TEXT,                   -- letzter Response-Handle fuer previous_response_id
    model_used           TEXT NOT NULL DEFAULT 'gpt-5.1',
    token_estimate       INTEGER NOT NULL DEFAULT 0,  -- Summe der aktiven (nicht komprimierten) Messages
    last_compaction_at   TEXT,                   -- NULL = noch nie komprimiert
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------
-- 3. chat_messages — neue Form, project_slug statt thread_id
-- ----------------------------------------------------------------
-- is_compacted=1 markiert Messages als archiviert (vor letzter Kompression).
-- Diese werden nicht mehr in den Agent-Context geladen, bleiben aber in
-- der DB fuer Datasette-Inspektion und UI-Anzeige mit Kompressions-Divider.
CREATE TABLE chat_messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_slug        TEXT NOT NULL,
    role                TEXT NOT NULL
                        CHECK (role IN ('user','assistant','tool','system')),
    content             TEXT,                   -- darf NULL sein bei reinen Tool-Calls
    tool_calls_json     TEXT,                   -- JSON-Array bei assistant-Messages
    tool_results_json   TEXT,                   -- JSON bei role='tool'
    foundry_message_id  TEXT,                   -- optional, aus Response-API
    tokens_input        INTEGER,
    tokens_output       INTEGER,
    token_count         INTEGER,                -- eigene Schaetzung fuer Kontext-Fill
    is_compacted        INTEGER NOT NULL DEFAULT 0
                        CHECK (is_compacted IN (0,1)),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_chat_messages_project
    ON chat_messages(project_slug, created_at);

CREATE INDEX idx_chat_messages_active
    ON chat_messages(project_slug, is_compacted, created_at);

COMMIT;
