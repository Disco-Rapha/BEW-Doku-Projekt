# Disco-Flows — Entwickler-Howto

Ein **Flow** ist ein projektinterner Verarbeitungs-Auftrag, der in einem
eigenen Python-Prozess läuft und eine typischerweise große Menge
gleichartiger Items abarbeitet. Von „Dateinamen parsen" über
„Excel-Report aus Tabellen-Joins" bis „DCC-Klassifikation mit gpt-5" —
alles ist ein Flow.

Dieses Paket liefert das **Framework**. Flows selbst liegen an zwei Orten:

1. **Library** (`src/disco/flows/library/<flow_name>/`) — globale
   Wiederverwendungs-Flows, die in **jedem** Projekt funktionieren.
   Einmal im Repo gepflegt, kein Kopieren pro Projekt noetig.
2. **Projekt-lokal** (`<projekt>/flows/<flow_name>/`) — Flows, die nur
   in diesem einen Projekt laufen oder einen Library-Flow bewusst
   ueberschreiben. Projekt-lokal gewinnt bei Namenskollision.

Aufloesungsreihenfolge beim Start (Service + runner_host):

```
<projekt>/flows/<name>/runner.py   →  falls vorhanden: nehmen
↓ sonst
disco/flows/library/<name>/runner.py  →  Library-Fallback
↓ sonst
Fehler: Flow existiert nicht.
```

## Anatomie eines Flows

```
<flow-root>/<flow_name>/
├── README.md        Pflicht — Anleitung für Disco + Nutzer
├── runner.py        Pflicht — Python-Code, der die Items verarbeitet
└── <was-auch-immer> Optional — prompt.md, schema.json, test-cases.jsonl, …
```

`<flow-root>` ist entweder `<projekt>/flows/` (lokal) oder
`src/disco/flows/library/` (global).

Die **README** ist zugleich Spec und Arbeitsprotokoll (Zweck, Input,
Output, Fehlerbehandlung, Kostenschätzung, Entscheidungen aus dem
Dialog zwischen Disco und Nutzer).

Der **runner.py** ist ein stinknormales Python-Skript mit einer
`main()`-Funktion. Es nutzt das SDK aus diesem Paket.

## Das SDK in 30 Sekunden

```python
from disco.flows.sdk import FlowRun, run_context

def process_one(item: dict) -> dict:
    # eigene Logik — gibt JSON-serialisierbares dict zurück
    return {"result": "…"}

def main() -> None:
    with run_context(FlowRun.from_env()) as run:
        # agent_sources ist Ebene 1 (datastore.db, attached als `ds`).
        items = run.db.query("SELECT id, rel_path FROM ds.agent_sources WHERE …")
        run.set_total(len(items))
        for item in items:
            run.process(
                input_ref=f"source:{item['id']}",
                fn=process_one,
                args=(item,),
            )

if __name__ == "__main__":
    main()
```

Was das SDK für dich macht:

- **Idempotenz** — Items, die als `done` in `agent_flow_run_items`
  stehen, werden beim Resume übersprungen.
- **Retry** — bei Exceptions in `fn` bis `max_retries` mit Backoff.
- **Pause/Cancel** — vor jedem Item wird geprüft, ob die UI oder der
  Agent pausieren/abbrechen will. Bei `pause_requested` wirft
  `process()` eine `FlowStopped`, die `run_context` als Ende-Signal
  behandelt.
- **Budget** — `run.add_cost(eur, tokens_in, tokens_out)` nach jedem
  LLM-/DI-Call; ist `config.budget_eur` gesetzt und überschritten,
  wird automatisch `pause_requested`.
- **Logging** — `run.log(msg)` schreibt nach
  `<projekt>/.disco/flows/runs/<run_id>/log.txt` und auf stderr.
- **Statistik** — `total_items`/`done_items`/`failed_items`/
  `skipped_items` werden atomar aktualisiert.

Du musst dich **nicht** um subprocess, Detachment, WAL-Locks, psutil,
PID-Tracking oder Thread-Sicherheit kümmern — das übernimmt
`runner_host.py`.

## Das Datenmodell

Zwei Projekt-DB-Tabellen (Migration `004_agent_flows.sql`):

| Tabelle | Zweck |
|---|---|
| `agent_flow_runs` | Ein Eintrag pro Run: Status, Stats, Control-Signale, Budget, Error |
| `agent_flow_run_items` | Ein Eintrag pro Item: input_ref, status, output_json, Fehler, Kosten |

UNIQUE-Index auf `(run_id, input_ref)` → Resume ist trivial.

## Lifecycle eines Runs

```
┌──────────┐     start_run        ┌──────────┐     pause           ┌────────┐
│ pending  │ ──────────────────→  │ running  │ ──────────────────→ │ paused │
└──────────┘                      └──────────┘                     └────┬───┘
                                     │  │  │                            │
                        runner.py    │  │  │  cancel              start │
                         done        │  │  └──────────→ cancelled ──────┘
                        ────────────→│  │
                            error    │  │
                        ────────────→└──┘ failed
```

Alle End-Zustände (`done`, `failed`, `cancelled`, `paused`) setzen
`finished_at`. Nur `paused` kann per `start_run` wieder aufgenommen
werden.

## CLI — so startet man Flows

```bash
# Flows im Projekt auflisten
disco flow list --project <slug>

# Details zu einem Flow (+ letzte Runs)
disco flow show <flow_name> --project <slug>

# Neuen Run starten (detached im Hintergrund)
disco flow run <flow_name> --project <slug> [--config '{"limit": 100}'] [--wait]

# Laufender Status
disco flow status <run_id> --project <slug>

# Liste aller Runs
disco flow runs --project <slug> [--flow <name>] [--status running]

# Items eines Runs
disco flow items <run_id> --project <slug> [--status failed]

# Pause / Cancel
disco flow pause <run_id> --project <slug>
disco flow cancel <run_id> --project <slug> [--force]

# Logs anschauen
disco flow logs <run_id> --project <slug> [--tail 100]
```

## Wo landet was?

| Artefakt | Ort |
|---|---|
| Flow-Code (lokal) | `<projekt>/flows/<flow_name>/` |
| Flow-Code (global) | `src/disco/flows/library/<flow_name>/` |
| Run-Logs (log.txt, stdout.log, stderr.log) | `<projekt>/.disco/flows/runs/<run_id>/` |
| Run-Stammdaten | `agent_flow_runs` |
| Item-Ergebnisse | `agent_flow_run_items` |

## Library-Flows: Erwartete Tabellen

Ein Library-Flow darf sich nur auf Tabellen verlassen, die in **jedem**
Projekt existieren — also Template-Migrationen unter
`migrations/project/NNN_*.sql`. Zusaetzliche `work_*`-Tabellen darf
der Runner selbst per `CREATE TABLE IF NOT EXISTS` anlegen.

Beispiele:
- `pdf_routing_decision` liest `agent_pdf_inventory` (Template 007) und
  schreibt `work_pdf_routing` (auch Template 007 + Runner-CREATE).

Will ein Library-Flow eine neue Tabelle einfuehren: **Migration anlegen**,
nicht ALTER-TABLE im Runner — damit das Schema in allen Projekten
konsistent bleibt.

## Was du dir sparst

- **Keine Subprocess-Experimente** — `runner_host` kennt Detachment,
  PID-Logging, SIGTERM.
- **Keine Datenbank-Lock-Drama** — SDK nutzt WAL, separate Connections
  pro FlowRun.
- **Keine Resume-Logik** — Idempotenz über UNIQUE-Index.
- **Keine eigene Budget-Buchhaltung** — `add_cost()` + `config.budget_eur`.
- **Kein manuelles Status-Setzen** — `run_context` ist der Lifecycle.

## Was DU leistest

- `runner.py` mit der fachlichen Logik.
- `README.md` mit Zweck, Input, Output, Fehlerbehandlung, Kosten,
  Entscheidungen (Disco pflegt die im Dialog).
- Die passende Input-Query (SQL auf `agent_sources` oder woanders).
- Die passende Item-Ref-Konvention (`source:<id>`, `file:<path>`, …).
