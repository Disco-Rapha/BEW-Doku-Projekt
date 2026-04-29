# Flow: extraction

## Flow auf einen Blick

| Aspekt           | Wert                                                                                       |
|------------------|--------------------------------------------------------------------------------------------|
| **Was**          | Generischer Extraktionsfluss fuer PDF, Excel, DWG, Bild — Engine-Dispatch.                  |
| **Eingabe**      | `work_extraction_routing` (Routing-Entscheidung pro Datei).                                  |
| **Verarbeitung** | Pro Datei: passenden Extractor aufrufen, Provenance-Header voranstellen, Side-Effects.       |
| **Ausgabe**      | `agent_doc_markdown` + `agent_doc_unit_offsets` (+ optional `context_*`-Tabellen).            |
| **Extern**       | Azure-DI (PDF/HR), Foundry GPT-5.1 (Bilder), lokal (Docling/openpyxl/ezdxf).                |
| **Budget**       | engine-abhaengig (s/Seite + EUR/Seite).                                                     |

```
work_extraction_routing ─▶ extraction ─▶ agent_doc_markdown
                                        ├─▶ agent_doc_unit_offsets
                                        └─▶ context_<slug>  (nur excel-table-import)
```

## Was es ersetzt

Diese Flow ersetzt `pdf_to_markdown`. `agent_pdf_markdown` und
`agent_pdf_page_offsets` wurden durch Migration `008_extraction_pipeline.sql`
in `agent_doc_markdown` und `agent_doc_unit_offsets` umbenannt.
Bestand bleibt erhalten (`file_kind='pdf'` als Default).

## Engine-Liste

| Engine                      | Format | Extractor                       | Cost-Approx        |
|-----------------------------|--------|---------------------------------|--------------------|
| `pdf-azure-di`              | pdf    | `disco.docs.pdf` → azure-di      | 8,68 EUR / 1000 p  |
| `pdf-azure-di-hr`           | pdf    | `disco.docs.pdf` → azure-di-hr   | 13,89 EUR / 1000 p |
| `pdf-docling-standard`      | pdf    | `disco.docs.pdf` → docling-standard | 0 EUR (lokal)   |
| `excel-openpyxl`            | excel  | `disco.docs.excel`              | 0 EUR              |
| `excel-table-import`        | excel  | `disco.docs.excel` + Tabellen-Side-Effect | 0 EUR     |
| `dwg-ezdxf-local`           | dwg    | `disco.docs.dwg`                | 0 EUR              |
| `image-gpt5-vision`         | image  | `disco.docs.image` → GPT-5.1     | ~Tokens × Preis    |

## Provenance-Header

Vor dem eigentlichen Markdown-Inhalt steht ein HTML-Kommentar-Block:

```markdown
<!-- provenance
file_id: 42
rel_path: sources/Geprueft/Datenblatt_Trafo.pdf
folder: sources/Geprueft
filename: Datenblatt_Trafo.pdf
file_kind: pdf
engine: pdf-azure-di
extracted_at: 2026-04-25T08:00:00Z
extractor_version: extraction-v3.0:pdf-azure-di:1.0
-->
```

- Im FTS-Index findbar (`search_index("Geprueft")` findet alle PDFs aus
  diesem Ordner)
- Beim Markdown-Rendern unsichtbar
- Vom LLM lesbar — Kontext zum Reasoning

## Side-Effect: excel-table-import

Bei `engine='excel-table-import'` (typisch fuer Excels in `context/`)
wird **zusaetzlich** zum Markdown jeder Sheet als SQL-Tabelle in
`workspace.db` angelegt:

- Bei einem Sheet: `context_<file_slug>`
- Bei mehreren Sheets: `context_<file_slug>__<sheet_slug>`

Erste Zeile = Header → Spaltennamen `col_<header_slug>`. Alle Werte als
TEXT. Bei Re-Import: alte Tabelle wird gedroppt und neu gefuellt
(idempotent).

`meta_json.imported_tables` enthaelt die Liste der angelegten Tabellen
mit Spalten + Zeilenanzahl.

## Konfiguration

```json
{
  "limit": 100,                          // optional, Testlauf
  "only_engine": "pdf-docling-standard", // optional, eine Engine isoliert
  "only_kind": "excel",                  // optional, ein Format isoliert
  "force_rerun": true,                    // optional, Skip-Logik aushebeln
  "model": "gpt-5.4-prod"                 // optional, LLM-Modell-Override
}
```

### `model` — Modell-Override fuer LLM-Engines

Wirkt nur auf LLM-basierte Engines (heute: `image-gpt5-vision`).
Andere Engines (DI, openpyxl, ezdxf) ignorieren das Feld.

**Default ohne `model`-Feld**: `gpt-5.1` (hardcoded in
`disco.docs.image.DEFAULT_FLOW_MODEL`). Bewusst NICHT die ENV-Variable
`FOUNDRY_MODEL_DEPLOYMENT` — die ist fuer den Disco-Agent (Chat)
reserviert (heute gpt-5.4-prod). Flow-Defaults sind kosten-orientiert.

Verfuegbare Modelle (Stand 2026-04):
- `gpt-5.1` (Default; Bulk-tauglich; ~30% guenstiger als gpt-5.4 bei
  Image-typischen Output-Mengen)
- `gpt-5.4-prod` (hoechste Qualitaet, teurer bei Output-lastigen
  Tasks — Cached-Input dafuer 90% Rabatt)

Die tatsaechlich genutzte Modell-ID landet in
`agent_doc_markdown.meta_json.deployment` (fuer Cost-Tracking).
Cost-Berechnung in `disco.pricing.compute_cost_eur()` nutzt
automatisch die richtigen Sweden-Central-Data-Zone-EUR-Preise pro Modell.

## Resume + Idempotenz

Default: Skip wenn `agent_doc_markdown.source_hash` == aktueller
`agent_sources.sha256`. Heisst: nur neue/geaenderte Dateien werden
extrahiert. Bei `force_rerun=true` werden alle Items frisch extrahiert
(alte Daten via REPLACE ueberschrieben).

## Versionierung

Pro Eintrag in `agent_doc_markdown` steht `extractor_version` der Form:

```
extraction-v3.0:<engine>:<engine-version>
```

Bei Code-Aenderung: Pipeline-Version (`disco.docs.EXTRACTION_PIPELINE_VERSION`)
oder Engine-Version (in den Engine-Modulen) hochzaehlen, dann
`force_rerun=true` triggern.
