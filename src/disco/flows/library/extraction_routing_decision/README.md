# Flow: extraction_routing_decision

## Flow auf einen Blick

| Aspekt           | Wert                                                                                          |
|------------------|-----------------------------------------------------------------------------------------------|
| **Was**          | Pro Datei (egal welches Format) Engine-Entscheidung fuer die Extraction-Pipeline.             |
| **Eingabe**      | `ds.agent_sources` (alle aktiven Dateien). Alternativ Rerun-Mode auf bestehende Engine-Bucket.|
| **Verarbeitung** | Pro Datei: file_kind ableiten, format-spezifische Heuristik anwenden.                          |
| **Ausgabe**      | `work_extraction_routing` mit `file_kind`, `engine`, `reason`, `heuristics_json`, Versionierung. |
| **Extern**       | Lokal — PyMuPDF (PDF), openpyxl (Excel), ezdxf optional (DWG), Pillow (Bild).                  |
| **Budget**       | 0 EUR, ~1 s pro Datei.                                                                        |

```
ds.agent_sources ─▶ extraction_routing_decision ─▶ work_extraction_routing
   alle Dateien      file_kind + Heuristik          engine ∈ ENGINES_BY_KIND[file_kind]
```

## Was es ersetzt

Diese Flow ersetzt den frueheren `pdf_routing_decision`-Flow. Daten in
`work_pdf_routing` wurden durch Migration `005_extraction_routing.sql`
nach `work_extraction_routing` umbenannt; `file_kind='pdf'` als Default
fuer alle Bestandseintraege.

## Engines pro file_kind

| file_kind | Engines (Default zuerst)                                   |
|-----------|------------------------------------------------------------|
| pdf       | `pdf-azure-di`, `pdf-azure-di-hr`, `pdf-docling-standard`  |
| excel     | `excel-openpyxl` (sources), `excel-table-import` (context) |
| dwg       | `dwg-ezdxf-local`                                          |
| image     | `image-gpt5-vision`                                        |

## Heuristiken

### PDF (3-Tier wie bisher, Stand 2026-04-25)

Sticky-Rules (strikte Reihenfolge):

1. `n_vdrawing_pages > 0` → `pdf-azure-di-hr` (KKS-Labels, Zeichnungskopf)
2. `max_page_width_pt > 1000` → `pdf-azure-di-hr` (A3+, feine Schriften)
3. `n_large_image_pages > 0` → `pdf-azure-di-hr` (Grossbild-OCR)
4. `n_scan_pages > 0` → `pdf-azure-di` (A4-Standard-OCR)
5. else → `pdf-azure-di` (Default seit Bench-Entscheid 2026-04-25, statt
   `pdf-docling-standard` wegen 4% Halluzinations-Rate)

### Excel

| file_role | Engine                | Begruendung                                    |
|-----------|------------------------|------------------------------------------------|
| context   | `excel-table-import`  | Lookup-Daten → SQL-Tabellen + Markdown          |
| source    | `excel-openpyxl`      | Suche/LLM-Lese → nur Markdown                   |

### DWG

Eine Engine: `dwg-ezdxf-local`. DXF wird direkt gelesen, DWG via
`ezdxf.addons.odafc` (ODA File Converter muss installiert sein).

### Bild

Eine Engine: `image-gpt5-vision` (Foundry GPT-5.1 multimodal). Standard-
Prompt liefert Beschreibung + OCR-Text + Strukturierte Erkennung.

## Konfiguration

```json
{
  "limit": 100,                          // optional, fuer Testlaeufe
  "rerun_where_engine": "pdf-azure-di-hr" // optional, neu routen
}
```

## Resume-Logik

Default: bereits geroutete `file_id`s (in `work_extraction_routing`) werden
uebersprungen. Mit `rerun_where_engine='<engine>'` werden nur die Dateien
neu geroutet, die heute auf dieser Engine sitzen — gut fuer Rollouts neuer
Heuristiken.

## Versionierung

`router_version` wird pro Eintrag mitgeschrieben (heute `router-v3.0`).
Bei Heuristik-Aenderung wird die Konstante in `disco.docs.routing`
hochgezaehlt.
