# Flow: pdf_routing_decision

## Flow auf einen Blick

| Aspekt           | Wert                                                                                                                      |
|------------------|---------------------------------------------------------------------------------------------------------------------------|
| **Was**          | 3-Tier-Routing pro PDF: `docling-standard`, `azure-di` oder `azure-di-hr`.                                                 |
| **Eingabe**      | `agent_pdf_inventory` (alle PDFs im Projekt). Alternativ Rerun-Mode auf eine bestehende Engine-Bucket.                      |
| **Verarbeitung** | Pro PDF: PyMuPDF-Analyse pro Seite (chars, n_paths, coverage, width); Dokument-Aggregation; 3-Tier-Entscheidung.            |
| **Ausgabe**      | Tabelle `work_pdf_routing` mit Engine, Begruendung, Seitenstatistik, neuen Signalen (`max_page_width_pt`, `n_large_image_pages`). |
| **Extern**       | Nur lokale PyMuPDF-Heuristik, keine Azure-Calls.                                                                           |
| **Budget**       | 0 EUR (CPU-only), ~1 s pro PDF, grob 25–30 Minuten fuer 1.500 PDFs.                                                        |

```
agent_pdf_inventory ─▶ pdf_routing_decision ─▶ work_pdf_routing
      PDFs              PyMuPDF + 3-Tier           engine ∈ {docling-standard, azure-di, azure-di-hr}
```

## Zweck

Der Flow trifft fuer **jedes PDF** eine Routing-Entscheidung zwischen drei Engines:

| Engine              | Kosten         | Einsatzgebiet                                                             |
|---------------------|----------------|---------------------------------------------------------------------------|
| `docling-standard`  | 0 EUR          | Reine Text-/Vektor-Dokumente (Produktblaetter, Formulare, Konformitaeten). |
| `azure-di`          | 0,00130 EUR/Seite | Scans auf A4-Normalformat ohne feine Schriften; DI-Standard-OCR reicht.   |
| `azure-di-hr`       | 0,00651 EUR/Seite | Vektor-Zeichnungen (KKS-Labels, Zeichnungskopf), Plan-Format (A3+), Grossbild-Seiten — 4x DPI noetig. |

Die Entscheidung basiert auf der kalibrierten pdf_classify-Heuristik plus drei neuen Signalen:
`n_vdrawing_pages`, `max_page_width_pt`, `n_large_image_pages`.

## Input

- **Tabelle**: `agent_pdf_inventory`
- **Felder**: `id` (als `file_id`), `rel_path`

**Zwei Lademodi:**

1. **Default (Resume-Mode)** — ueberspringt alle bereits in `work_pdf_routing` eingetragenen `file_id`.
2. **Rerun-Mode** via `config.rerun_where_engine = "azure-di-hr"` (o. ae.) — waehlt genau die file_ids,
   die aktuell mit dieser Engine markiert sind, und routet sie mit der aktuellen Heuristik neu.
   Kombinierbar mit `limit`. `ORDER BY RANDOM()` fuer eine zufaellige Stichprobe.

## Verarbeitung pro Item

1. **PDF oeffnen** — `fitz.open(pdf_path)`. Fehlende Datei → `failed`.

2. **Pro Seite** (via PyMuPDF):
   - `chars`, `n_paths`, `n_images`
   - `text_coverage`, `vector_coverage`, `image_coverage` (Flaeche / Seitenflaeche)
   - `width_pt` (fuer `max_page_width_pt` auf Dokumentebene)

3. **Seiten-Kind bestimmen** (unveraendert zur v1-Kalibrierung):
   1. `empty` — `chars<20 ∧ n_paths=0 ∧ image_cov<0.10`
   2. `scan` (klassisch) — `chars<50 ∧ image_cov>0.50`
   3. `scan` (mit OCR-Layer) — `(vec_cov + img_cov) > 0.50 ∧ text_cov < 0.40 ∧ chars < 3500`
   4. Text-Dominanz (`chars≥1000 ∧ text_cov≥0.30`): `mixed` bei heavy graphics, sonst `text`
   5. `vector-drawing` — `vec_cov > 0.40 ∧ chars < 500`
   6. Rest: `mixed` oder `text`

4. **Dokument-Aggregation:**
   - `n_pages`, `kind_counts_json`, `n_scan_pages`, `n_vdrawing_pages`, `n_text_pages`, `n_mixed_pages`
   - `max_page_width_pt` = `max(width_pt)` ueber alle Seiten
   - `n_large_image_pages` = Anzahl Seiten mit `image_coverage > 0.60`

5. **3-Tier-Routing (strikte Reihenfolge, Sticky-Rule):**

   ```
   1) n_vdrawing_pages ≥ 1
        → azure-di-hr  (KKS-Labels / Zeichnungskopf brauchen 4x DPI)

   2) max_page_width_pt > 1000 pt  (A3-Landscape+)
        → azure-di-hr  (Plan-Format, feine Schriften)

   3) n_large_image_pages ≥ 1  (image_coverage > 0.60 auf mindestens 1 Seite)
        → azure-di-hr  (Grossbild/Foto/Explosionszeichnung → Detail-OCR)

   4) n_scan_pages ≥ 1
        → azure-di     (A4-Scan ohne Plan/Grossbild/Vektorzeichnung — Standard-OCR reicht)

   5) sonst
        → azure-di     (INTERIM 2026-04-24: zuvor docling-standard, umgestellt
                        solange die Docling-Qualitaet nicht ueberzeugt. Alte
                        docling-Markdown-Eintraege werden NICHT neu extrahiert.)
   ```

   Schwellen:
   - `_PLAN_FORMAT_MIN_WIDTH_PT = 1000.0`
     - A4-Landscape = 842 pt (NICHT getriggert)
     - A3-Landscape = 1191 pt → getriggert
   - `_LARGE_IMAGE_MIN_COVERAGE = 0.60`

6. **Ergebnis schreiben** — `INSERT OR REPLACE` auf `file_id`.

## Output

Tabelle `work_pdf_routing`:

| Spalte                  | Typ     | Inhalt                                                                     |
|-------------------------|---------|----------------------------------------------------------------------------|
| `file_id`               | INTEGER | PK                                                                          |
| `rel_path`              | TEXT    |                                                                             |
| `n_pages`               | INTEGER |                                                                             |
| `kind_counts_json`      | TEXT    | JSON, keys: empty/scan/vector-drawing/mixed/text                           |
| `n_scan_pages`          | INTEGER |                                                                             |
| `n_vdrawing_pages`      | INTEGER |                                                                             |
| `n_text_pages`          | INTEGER |                                                                             |
| `n_mixed_pages`         | INTEGER |                                                                             |
| `share_scan_or_vdrawing`| REAL    | `(scan+vdrawing)/n_pages`                                                   |
| `max_page_width_pt`     | REAL    | **NEU** — max Seitenbreite ueber alle Seiten (pt)                          |
| `n_large_image_pages`   | INTEGER | **NEU** — Anzahl Seiten mit `image_coverage > 0.60`                        |
| `engine`                | TEXT    | `docling-standard` \| `azure-di` \| `azure-di-hr`                          |
| `reason`                | TEXT    |                                                                             |
| `duration_ms`           | REAL    |                                                                             |
| `run_id`                | INTEGER |                                                                             |
| `created_at`            | TEXT    | ISO-Timestamp (UTC)                                                         |

## Parameter (config_json)

- `limit` *(int, optional)* — max Anzahl Items
- `rerun_where_engine` *(str, optional)* — wenn gesetzt, waehle file_ids mit diesem Engine-Wert
  in `work_pdf_routing` und route sie mit der aktuellen Heuristik neu. Z. B.:
  `{"rerun_where_engine": "azure-di-hr", "limit": 100}` → 100 zufaellig gezogene bisherige
  DI-HR-Docs werden neu bewertet.

## Fehlerbehandlung & Resume

- Bereits geroutete Zeilen werden im Default-Mode uebersprungen.
- Rerun-Mode ignoriert die Skip-Logik und ersetzt die Zeilen.
- Fehler beim Oeffnen/Parsen → Item landet als `failed` im Flow-Run.

## Wie erkennst Du, dass es funktioniert hat

- `SELECT engine, COUNT(*) FROM work_pdf_routing GROUP BY engine` zeigt die Buckets
  (in Interim-Phase meist nur `azure-di` + `azure-di-hr`; `docling-standard` nur
  fuer Alt-Eintraege).
- Stichprobe:
  - Produktdatenblaetter A4 ohne Scans → `azure-di` (interim, zuvor `docling-standard`)
  - A4-Scan-Handbuecher (DIN A4 Portrait) ohne Zeichnungen → `azure-di`
  - Technische Zeichnungen mit Zeichnungskopf → `azure-di-hr` (vdrawing oder Plan-Format)
  - Dokumente mit eingeklebten Foto-/Explosions-Seiten → `azure-di-hr`

## Entscheidungen

- 2026-04-22 — v1: Binary `docling-standard` vs. `azure-di-hr`, Sticky-Rule auf scan/vdrawing.
- 2026-04-22 — v2: 3-Tier-Routing, `azure-di` als Mittelstufe fuer A4-Scans ohne HR-Bedarf,
  neue Signale `max_page_width_pt` + `n_large_image_pages`.
- 2026-04-24 — Interim-Switch: Fallback von `docling-standard` auf `azure-di`. Grund:
  Docling-Qualitaet nicht ueberzeugend. `docling-standard` bleibt als Engine im System
  (Alt-Eintraege + spaeteres Reaktivieren). Rueckroll = else-Branch im Runner wieder auf
  `engine = "docling-standard"` setzen.

## Historie

- 2026-04-22 — v1: Initiale Version des Binary-Routing-Flows. Full-Run Run #5:
  422 → azure-di-hr, 1109 → docling-standard, 1 failed (leere PDF).
- 2026-04-22 — v2: 3-Tier-Update. Ziel: Reduktion der HR-Seiten, wenn DI-Standard-OCR reicht.
- 2026-04-24 — Interim: Standard-Fallback `docling-standard` → `azure-di` (kein Schema-
  Change, nur Entscheidungslogik im Runner). Alte Markdown-Eintraege bleiben unberuehrt.
