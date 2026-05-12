-- 010_agent_egress_violations.sql
-- ===========================================================================
-- Audit-Trail fuer geblockte externe Netzwerk-Verbindungen aus Disco-
-- Subprocesses (run_python und Flow-Runner).
--
-- Disco soll lokal-first arbeiten und nur zu definierten externen
-- Endpoints reden (Azure Foundry, Azure DI in Sweden Central). Der
-- _network_guard.py injiziert in jeden Subprocess Patches auf
-- socket.create_connection / socket.socket.connect / ssl.SSLSocket
-- und blockt alles ausserhalb der Whitelist. Jeder Block-Versuch
-- landet hier — sichtbar, untersuchbar, mandantenuebergreifend (in
-- system.db, nicht workspace.db, weil Egress-Compliance projekt-
-- uebergreifend monitored wird).
--
-- Schreibvorgang: aus dem _network_guard.py per direktem
-- sqlite3.connect(system.db) -- KEIN ORM, kein Disco-Code, weil
-- der Guard auch in fremden Subprocess-Kontexten greift.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS agent_egress_violations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT NOT NULL DEFAULT (datetime('now')),

    -- Wer hat den Block ausgeloest:
    --   'run_python'   = direkter Agent-Subprocess via executor.py
    --   'flow-runner'  = Flow-Subprocess via runner_host.py
    --   'other'        = sonstige Subprocesses (Reserve)
    source          TEXT NOT NULL CHECK (source IN ('run_python', 'flow-runner', 'other')),

    -- Welcher Host wurde versucht (Hostname wenn aufloesbar, sonst IP)
    attempted_host  TEXT NOT NULL,
    attempted_port  INTEGER,

    -- Kontext (alle optional, je nach Quelle):
    project_slug    TEXT,       -- aus contextvars wenn vorhanden
    script_path     TEXT,       -- bei run_python: das .py
    run_id          INTEGER,    -- bei flow-runner: der flow_run_id
    pid             INTEGER,    -- Subprocess-PID zum Debuggen

    -- Stack-Trace-Kurzfassung (max ~2000 chars) — hilft beim
    -- Identifizieren welche Library den Call versucht hat (httpx?
    -- urllib? requests?)
    stack_summary   TEXT
);

CREATE INDEX IF NOT EXISTS idx_egress_violations_occurred
    ON agent_egress_violations(occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_egress_violations_project
    ON agent_egress_violations(project_slug, occurred_at DESC);
