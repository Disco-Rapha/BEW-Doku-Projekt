# Flow: pdf_to_markdown

## Flow auf einen Blick

| Aspekt           | Wert                                                                                           |
|------------------|------------------------------------------------------------------------------------------------|
| **Was**          | Liest die Routing-Entscheidung und extrahiert jede PDF einmal nach Markdown.                    |
| **Eingabe**      | `work_pdf_routing` (file_id, engine) + `agent_pdf_inventory` (rel_path, sha256).                |
| **Verarbeitung** | Pro PDF: Dispatcher ruft `docling-standard` / `azure-di` / `azure-di-hr` auf.                   |
| **Ausgabe**      | `agent_pdf_markdown` (md_content + char_count + source_hash + duration_ms + cost).              |
| **Extern**       | Nur fuer `azure-di*` → Azure Document Intelligence. `docling-standard` ist lokal.               |
| **Budget**       | docling-standard = 0 EUR; azure-di ~0,01 EUR/Seite; azure-di-hr ~0,015 EUR/Seite.               |

```
agent_pdf_inventory  +  work_pdf_routing   ─▶  pdf_to_markdown  ─▶  agent_pdf_markdown
          rel_path            engine              Dispatcher              md_content
```

## Zweck

Nach dem vorgelagerten Routing-Flow (`pdf_routing_decision`) hat jede PDF
in `work_pdf_routing` eine Engine-Zuordnung. Dieser Flow fuehrt die
eigentliche Extraktion aus und schreibt das Ergebnis **einmal** in die
Tabelle `agent_pdf_markdown`. Ab diesem Moment ist `md_content` die
alleinige Wahrheit fuer inhaltliche Fragen — der Agent greift nicht
mehr direkt auf die PDFs zurueck.

## Input

- **Tabelle**: `work_pdf_routing` (PK `file_id`).
- **Join**: `agent_pdf_inventory` (fuer `rel_path` und `sha256`).
- **Filter**: nur Zeilen mit gesetzter `engine`; bereits extrahierte
  `file_id`s mit unveraendertem `source_hash` werden uebersprungen.

## Verarbeitung pro Item

1. **Pfad + Hash laden** — `agent_pdf_inventory.sha256` wird als
   `source_hash` mitgeschrieben, damit spaeter erkannt werden kann,
   ob eine neue Extraktion noetig ist (Datei hat sich geaendert).
2. **Dispatcher-Call** — `disco.pdf.extract_markdown(path, engine)`
   liefert `(md, meta)`.
3. **Schreiben** — `INSERT OR REPLACE` in `agent_pdf_markdown`.
   Leere Markdown-Ausgabe wird als leerer String gespeichert —
   NICHT NULL, damit "extrahiert, aber leer" unterscheidbar bleibt.
4. **Kosten verbuchen** — `run.add_cost(eur=meta["estimated_cost_eur"])`.
5. **Fehler** — Exception → Item `failed`, `max_retries=1`. Azure-429
   oder Auth-Fehler werden nicht maskiert.

## Output

Tabelle `agent_pdf_markdown` (Template 008):

| Spalte        | Typ     | Inhalt                                          |
|---------------|---------|-------------------------------------------------|
| `file_id`     | INTEGER | PK, FK auf `agent_pdf_inventory.id`             |
| `rel_path`    | TEXT    | Pfad relativ zum Projekt-Root                    |
| `engine`      | TEXT    | `docling-standard` \| `azure-di` \| `azure-di-hr` |
| `md_content`  | TEXT    | Markdown (leerer String erlaubt, NULL nicht)     |
| `char_count`  | INTEGER | `len(md_content)`                                |
| `source_hash` | TEXT    | SHA-256 der Quelldatei zum Extraktionszeitpunkt  |
| `duration_ms` | REAL    |                                                  |
| `run_id`      | INTEGER |                                                  |
| `created_at`  | TEXT    | ISO-Timestamp (UTC)                              |

## Parameter (config_json)

- `limit` *(int, optional)* — max Anzahl Items pro Lauf.
- `only_engine` *(str, optional)* — beschraenkt auf eine Engine
  (`docling-standard` / `azure-di` / `azure-di-hr`), z. B. erst die
  0-EUR-Bucket durchziehen, dann Azure.
- `force_rerun` *(bool, optional)* — ignoriert die Hash-Skip-Logik und
  extrahiert neu, auch wenn `source_hash` unveraendert ist.

## Fehlerbehandlung & Resume

- Default: Zeilen mit unveraendertem `source_hash` werden
  uebersprungen. Aenderungen an der PDF (neuer Hash) loesen eine
  Neu-Extraktion automatisch aus.
- `force_rerun=true` ignoriert die Skip-Logik.
- Fehler beim Extrahieren → Item landet als `failed`. Kosten aus
  Teil-Erfolgen (Azure-Call durch, aber DB-Fehler) werden verbucht.

## Wie erkennst Du, dass es funktioniert hat

- `SELECT engine, COUNT(*), ROUND(AVG(char_count)) FROM agent_pdf_markdown GROUP BY engine`
  zeigt drei Buckets mit plausiblen Durchschnittsgroessen.
- Stichprobe: `SELECT md_content FROM agent_pdf_markdown WHERE file_id=?`
  liefert gut formatiertes Markdown mit Tabellen und Seiten-Markern.
- Fuer Azure-Extrakte: `SELECT SUM(estimated_cost_eur) …` aus
  `agent_flow_runs.cost_eur_total` deckt sich grob mit DI-Abrechnung.

## Entscheidungen

- 2026-04-22 — v1: Drei Engines (docling-standard, azure-di, azure-di-hr),
  kein VLM-Pfad, kein pypdf. Leere Extrakte werden als `''` gespeichert,
  nicht NULL (User-Entscheid: "leer sonst speichern").
- 2026-04-22 — v1: Kein `engine_version`-Feld. Rerun bei Engine-
  Kalibrierung erfolgt manuell per `force_rerun=true`.

## Historie

- 2026-04-22 — v1: Initialversion. Ziel: UAT-Projekt (32 PDFs) komplett
  nach Markdown durchziehen.
