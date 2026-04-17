-- Projekt-DB-Template 004: Flows — Massenverarbeitung mit Lifecycle
--
-- Ein Flow ist ein projektinterner Verarbeitungs-Auftrag, der in einem
-- eigenen Unterprozess laeuft. Die Flow-Definition (README.md +
-- runner.py + Hilfsdateien) liegt unter <projekt>/flows/<flow_name>/.
--
-- Diese Tabellen halten den Laufzeit-Zustand:
--
--   agent_flow_runs       — ein Eintrag pro Run eines Flows
--                            (Status, Stats, Control-Signale)
--   agent_flow_run_items  — ein Eintrag pro Item innerhalb eines Runs
--                            (Input-Referenz, Output-JSON, Fehler, Kosten)
--
-- Unsere Flow-Tabellen folgen der agent_*-Namespace-Konvention:
-- Disco darf sie per sqlite_query lesen, aber nicht per sqlite_write
-- anpassen — die Pflege uebernimmt ausschliesslich das Flow-SDK.
--
-- Idempotenz und Resume:
--   Pro (run_id, input_ref) gibt es genau einen Eintrag in
--   agent_flow_run_items. Wird ein Run mehrfach gestartet oder nach
--   einem Abbruch fortgesetzt, werden 'done'-Items uebersprungen und
--   nur 'pending'/'failed' neu angegangen (Retry-Logik im SDK).

BEGIN;

-- ----------------------------------------------------------------
-- agent_flow_runs — ein Eintrag pro Flow-Run
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_flow_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_name           TEXT NOT NULL,      -- matcht <projekt>/flows/<flow_name>/
    title               TEXT,                -- kurze menschenlesbare Beschreibung

    -- Lifecycle
    status              TEXT NOT NULL DEFAULT 'pending',
                        -- 'pending'   — angelegt, Worker noch nicht gestartet
                        -- 'running'   — Worker laeuft aktiv
                        -- 'paused'    — pausiert (Budget, User, Anomalie)
                        -- 'done'      — erfolgreich abgeschlossen
                        -- 'failed'    — abgebrochen wegen Fehler
                        -- 'cancelled' — vom Nutzer abgebrochen
    worker_pid          INTEGER,             -- PID des Worker-Prozesses

    -- Konfiguration beim Start (Parameter aus der README)
    config_json         TEXT,                -- z.B. {"limit": 100, "budget_eur": 15}

    -- Zaehler (werden vom SDK laufend aktualisiert)
    total_items         INTEGER NOT NULL DEFAULT 0,
    done_items          INTEGER NOT NULL DEFAULT 0,
    failed_items        INTEGER NOT NULL DEFAULT 0,
    skipped_items       INTEGER NOT NULL DEFAULT 0,

    -- Kosten-Tracking (fuer LLM-/DI-basierte Flows)
    total_cost_eur      REAL NOT NULL DEFAULT 0.0,
    total_tokens_in     INTEGER NOT NULL DEFAULT 0,
    total_tokens_out    INTEGER NOT NULL DEFAULT 0,

    -- Control-Signale (vom User/Agent gesetzt, vom Worker beobachtet)
    pause_requested     INTEGER NOT NULL DEFAULT 0,  -- 1 = pausieren beim naechsten Item
    cancel_requested    INTEGER NOT NULL DEFAULT 0,  -- 1 = abbrechen beim naechsten Item

    -- Fehler auf Run-Ebene (nicht pro Item)
    error               TEXT,

    -- Zeitstempel
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    started_at          TEXT,
    finished_at         TEXT,

    -- Sanity-Check Status
    CHECK (status IN ('pending','running','paused','done','failed','cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_flow_runs_status
    ON agent_flow_runs(status);
CREATE INDEX IF NOT EXISTS idx_flow_runs_flow_name
    ON agent_flow_runs(flow_name);
CREATE INDEX IF NOT EXISTS idx_flow_runs_created
    ON agent_flow_runs(created_at);

-- ----------------------------------------------------------------
-- agent_flow_run_items — ein Eintrag pro Item innerhalb eines Runs
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_flow_run_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES agent_flow_runs(id) ON DELETE CASCADE,

    -- Eindeutige Referenz auf das Input-Item innerhalb dieses Runs.
    -- Konvention: "<art>:<id-oder-pfad>"
    --   "source:123"           — agent_sources.id
    --   "file:context/foo.pdf" — freier Pfad relativ zum Projekt
    --   "row:42"               — Zeile aus einer importierten Tabelle
    input_ref       TEXT NOT NULL,

    -- Lifecycle pro Item
    status          TEXT NOT NULL DEFAULT 'pending',
                    -- 'pending' — noch nicht bearbeitet
                    -- 'running' — aktuell in Bearbeitung (fuer Sichtbarkeit)
                    -- 'done'    — erfolgreich, output_json gefuellt
                    -- 'failed'  — Fehler, error gefuellt
                    -- 'skipped' — vom Flow bewusst uebersprungen
    attempts        INTEGER NOT NULL DEFAULT 0,

    -- Ergebnis
    output_json     TEXT,       -- beliebiges JSON, vom Flow bestimmt
    error           TEXT,       -- bei 'failed': kurze Fehlermeldung

    -- Kosten fuer dieses Item (summiert sich in agent_flow_runs.total_*)
    tokens_in       INTEGER NOT NULL DEFAULT 0,
    tokens_out      INTEGER NOT NULL DEFAULT 0,
    cost_eur        REAL NOT NULL DEFAULT 0.0,

    -- Zeitstempel
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    finished_at     TEXT,

    CHECK (status IN ('pending','running','done','failed','skipped'))
);

-- Eindeutigkeit: pro Run jede input_ref genau einmal.
-- Damit ist Resume trivial (INSERT OR IGNORE) und Doppelverarbeitung unmoeglich.
CREATE UNIQUE INDEX IF NOT EXISTS idx_flow_run_items_unique
    ON agent_flow_run_items(run_id, input_ref);

-- Wichtigster Worker-Index: pending-Items eines Runs schnell finden
CREATE INDEX IF NOT EXISTS idx_flow_run_items_run_status
    ON agent_flow_run_items(run_id, status);

COMMIT;
