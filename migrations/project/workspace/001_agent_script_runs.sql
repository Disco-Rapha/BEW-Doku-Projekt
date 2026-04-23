-- Projekt-DB-Template 003: agent_script_runs
--
-- Audit-Trail fuer alle Python-Skript-Ausfuehrungen die Disco (oder der
-- User manuell) ueber das run_python-Tool anstossen. Jede Ausfuehrung
-- wird mit Exit-Code, Dauer, stdout/stderr-Vorschau und ggf. Fehler
-- protokolliert.
--
-- Nutzen:
--   - Nachvollziehbarkeit: "Was hat Disco gestern laufen lassen?"
--   - Debugging: stderr der letzten Laeufe eines Skripts einsehen
--   - Wiederholung: Skript-Pfad + args nachschlagen, nochmal starten

BEGIN;

CREATE TABLE IF NOT EXISTS agent_script_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    script_path     TEXT,              -- relativ zum Projekt (NULL bei inline)
    inline_hash     TEXT,              -- sha256 des Inline-Codes (NULL bei file)
    mode            TEXT NOT NULL DEFAULT 'file',  -- 'file' | 'inline'
    args            TEXT,              -- JSON-Array der CLI-Argumente
    exit_code       INTEGER,           -- 0 = OK, >0 = Fehler, NULL = Timeout/Crash
    duration_s      REAL,
    stdout_preview  TEXT,              -- erste 2000 Zeichen stdout
    stderr_preview  TEXT,              -- erste 2000 Zeichen stderr
    stdout_bytes    INTEGER,           -- volle Laenge stdout in Bytes
    stderr_bytes    INTEGER,           -- volle Laenge stderr in Bytes
    truncated       INTEGER NOT NULL DEFAULT 0,  -- 1 wenn stdout/stderr gekappt
    error           TEXT,              -- Python-Exception oder Timeout-Meldung (intern)
    triggered_by    TEXT NOT NULL DEFAULT 'agent',  -- 'agent' | 'user' | 'job'
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_script_runs_path
    ON agent_script_runs(script_path);
CREATE INDEX IF NOT EXISTS idx_script_runs_started
    ON agent_script_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_script_runs_exit
    ON agent_script_runs(exit_code);

COMMIT;
