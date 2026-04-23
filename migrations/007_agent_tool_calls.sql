-- 007_agent_tool_calls.sql
-- Observability + User-Feedback fuer Agent-Turns.
--
-- Ziel: Tool-Call-Rohdaten aus chat_messages.tool_calls_json / tool_results_json
-- in eine strukturierte Tabelle spiegeln, damit wir ohne JSON-Parsing ueber alle
-- Projekte aggregieren koennen (Was wird wie oft gerufen? Wo gibt es Fehler?
-- Wie lange dauern die Aufrufe? Welche Sequenzen sind typisch?).
--
-- Zusaetzlich chat_message_feedback, damit der Nutzer im UI pro Assistant-Message
-- "gut"/"suboptimal" + Kommentar hinterlassen kann. Diese Signale fuettern das
-- spaetere Eval-Set.

-- ---------------------------------------------------------------------------
-- agent_tool_calls
-- ---------------------------------------------------------------------------
-- Eine Zeile pro Tool-Call. message_id zeigt auf den assistant-Turn, der den
-- Call angefordert hat; result_message_id auf den zugehoerigen tool-Turn mit
-- dem Ergebnis (nullable — falls das Ergebnis nie zurueckkam).
-- Die Duration wird aus der Differenz der beiden created_at-Stempel abgeleitet.

CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id           INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    result_message_id    INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,
    project_slug         TEXT NOT NULL,                           -- denormalisiert fuer schnelle Filter
    tool_call_id         TEXT,                                    -- Foundry-Id zum Joinen mit result
    tool_name            TEXT NOT NULL,
    arguments_json       TEXT,                                    -- Raw-Argumente (JSON)
    arguments_summary    TEXT,                                    -- kompakte One-Liner-Repraesentation
    result_summary       TEXT,                                    -- erste 500 Zeichen des Ergebnisses
    result_is_error      INTEGER NOT NULL DEFAULT 0
                         CHECK (result_is_error IN (0, 1)),
    result_error_msg     TEXT,
    duration_ms          INTEGER,                                 -- aus created_at-Differenz
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_project
    ON agent_tool_calls(project_slug, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_tool
    ON agent_tool_calls(tool_name, result_is_error);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_message
    ON agent_tool_calls(message_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_tool_calls_unique
    ON agent_tool_calls(message_id, tool_call_id);

-- ---------------------------------------------------------------------------
-- chat_message_feedback
-- ---------------------------------------------------------------------------
-- Ein Eintrag pro Feedback-Event. Ein Nutzer kann Feedback nachtraeglich
-- aendern (neuer Eintrag; der neueste gilt). Der Kommentar ist optional.

CREATE TABLE IF NOT EXISTS chat_message_feedback (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    project_slug  TEXT NOT NULL,                                  -- denormalisiert
    rating        TEXT NOT NULL CHECK (rating IN ('good', 'bad')),
    comment       TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_message_feedback_message
    ON chat_message_feedback(message_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_message_feedback_rating
    ON chat_message_feedback(rating, created_at);
