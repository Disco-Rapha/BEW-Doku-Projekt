-- Projekt-DB-Template 005: Flow-Notifications fuer System-getriggerte
-- Disco-Turns ("Disco ueberwacht den Run").
--
-- Idee: Der Worker schreibt nach bestimmten Ereignissen (erstes Item
-- fertig, zweites Item fertig, Halbzeit, Heartbeat, Status-Wechsel,
-- Done, Failed) eine Notification in die Tabelle. Ein Backend-Watcher
-- pollt diese Tabelle, baut den Trigger-Kontext und startet einen
-- System-getriggerten Disco-Turn.
--
-- Heartbeat mit exponentiellem Backoff:
--   1 min, 2, 4, 8, 16, 32, 64, 128, 256 min, ...  Cap bei 240 min (4 h).
--   Idee vom Nutzer: anfangs viel Aufmerksamkeit (systematische Fehler
--   fallen sofort auf), spaeter nur sporadisch (Token-Sparsamkeit).
--
-- last_payload: Der letzte Item-Output ist bereits als
--   agent_flow_run_items.output_json verfuegbar — keine neue Spalte
--   noetig, der Watcher zieht ihn beim Trigger-Bau aus der Tabelle.

BEGIN;

-- ----------------------------------------------------------------
-- agent_flow_notifications — eine Zeile pro Trigger-Ereignis
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_flow_notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES agent_flow_runs(id) ON DELETE CASCADE,

    -- Trigger-Art:
    --   'first_item'    — erstes Item dieses Runs ist done/failed
    --   'second_item'   — zweites Item ist done/failed
    --   'half'          — done_items >= total_items / 2 (einmalig)
    --   'heartbeat'     — naechstes Heartbeat-Intervall erreicht
    --   'status_change' — Run wechselt Status (running/paused/done/failed/cancelled)
    --   'done'          — Run abgeschlossen (status='done')
    --   'failed'        — Run abgebrochen (status='failed' oder 'cancelled')
    kind            TEXT NOT NULL,

    -- Snapshot des Triggers — vom Worker zusammengeschnuert.
    -- Beispiel:
    --   {"done": 50, "total": 100, "failed": 0, "cost": 0.03,
    --    "last_status": "running", "new_status": "running",
    --    "elapsed_sec": 720,
    --    "last_items": [{"input_ref":"source:47","output_json":{...}}, ...]}
    -- Beim Trigger-Bau zieht der Watcher noch zusaetzlich die Logs
    -- und das Flow-README, packt alles in den Foundry-Prompt.
    context_json    TEXT,

    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    -- NULL = wartet auf Verarbeitung, gesetzt = Watcher hat einen
    -- System-Turn ausgeloest (oder bewusst uebersprungen)
    processed_at    TEXT,

    CHECK (kind IN ('first_item','second_item','half','heartbeat',
                    'status_change','done','failed'))
);

CREATE INDEX IF NOT EXISTS idx_flow_notifications_pending
    ON agent_flow_notifications(processed_at, created_at)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_flow_notifications_run
    ON agent_flow_notifications(run_id, kind);

-- ----------------------------------------------------------------
-- agent_flow_runs erweitern: Heartbeat-Steuerung
-- ----------------------------------------------------------------
-- next_heartbeat_at: Wann ist der naechste Heartbeat faellig (Datetime
-- als ISO-String). NULL = kein Heartbeat geplant (z.B. Run pausiert
-- oder gerade beendet).
ALTER TABLE agent_flow_runs ADD COLUMN next_heartbeat_at TEXT;

-- last_heartbeat_interval_sec: Letzter Intervall in Sekunden. Wird
-- bei jedem Heartbeat-Trigger verdoppelt (Backoff). Initial 60 (1 min).
-- Cap bei 14400 (4 h).
ALTER TABLE agent_flow_runs ADD COLUMN last_heartbeat_interval_sec INTEGER NOT NULL DEFAULT 60;

COMMIT;
