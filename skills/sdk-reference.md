---
name: sdk-reference
description: Pflicht-Workflow + Anti-Halluzinations-Regeln, wenn Du einen Flow mit Azure Document Intelligence, Azure OpenAI (Structured Output) oder dem Engine-Dispatcher (`disco.pdf.extract_markdown`) baust. Code-Snippets stehen in `docs/sdk-reference.md` — gezielt nachschlagen, nicht aus dem Kopf tippen.
when_to_use: "Azure Document Intelligence", "DI", "prebuilt-layout", "ocrHighResolution", "OCR", "Azure OpenAI", "GPT-5 API", "Structured Output", "response_format", "json_schema", "AzureKeyCredential", "Docling", "extract_markdown", IMMER wenn Du einen Flow mit externem Azure-Call ODER Engine-Dispatcher-Aufruf baust.
---

# Skill: sdk-reference

Du hast **kein Internet**, und Deine Trainingsdaten sind für
Azure-SDK-Signaturen **nicht verlässlich**. Wenn Du einen DI- oder
LLM-Call baust: **erst nachschlagen, dann schreiben** — nicht
improvisieren.

Die Code-Snippets stehen in [`docs/sdk-reference.md`](../docs/sdk-reference.md).
Gezielt holen, was Du brauchst:

```text
fs_read("docs/sdk-reference.md", section="Azure Document Intelligence")
fs_read("docs/sdk-reference.md", section="Strukturierter JSON-Output")
fs_read("docs/sdk-reference.md", section="run.db.insert_row")
```

## Drei harte Regeln — niemals halluzinieren

1. **Keine `disco.services.*`-Imports erfinden.** So ein Modul gibt
   es nicht. Direkt das offizielle Azure-SDK importieren.
2. **Keine Parameter raten.** `content=data`, `file_bytes=...`,
   `document=...` — gibt es alles nicht. Die korrekten Parameter
   stehen im Doc, zeichengenau.
3. **Kein `try/except ImportError`-Fallback mit weichen Fehlern.**
   Wenn das SDK fehlt → harter `RuntimeError`, der Flow bricht ab
   und das Problem ist sofort sichtbar (statt 20 Items später).

## Engine-Wahl bei PDF-Extraktion

| Engine | Wann | Kosten |
|---|---|---|
| `docling-standard` | Text + Tabellen, evtl. Scans (Default) | 0 EUR |
| `azure-di` | A4-Scans, wenig Text | 0,00868 EUR/Seite |
| `azure-di-hr` | vector-drawing, Plan-Format, große Bilder | 0,01389 EUR/Seite |

Braucht ein Flow ad hoc Markdown, ruft er `extract_markdown(abs_path,
engine)` aus `disco.pdf` — kein Direkt-Kontakt zu Docling oder DI,
die Engine-Logik ist im Dispatcher gekapselt. Details + Offline-Modus
in [`docs/sdk-reference.md`](../docs/sdk-reference.md).

## Pflicht-Regeln für jeden LLM-Call

- **Cost-Tracking ist Pflicht** — `run.add_cost_from_azure_response(response)`
  direkt nach jedem `client.chat.completions.create(...)`-Aufruf.
  Ohne den Helper bleibt `total_cost_eur = 0` und das UI zeigt
  falsche Budgets (UAT-Bug #10). Kein Ausnahmefall.
- **Structured Output statt Freitext-JSON** — `response_format=
  {"type": "json_schema", "json_schema": <schema>}` mit
  `strict: True`, `additionalProperties: False`, alle Properties in
  `required`. Spart eigenes Parsing und Halluzinations-Cleanup.
- **`temperature` weglassen** — gpt-5 lehnt jeden Wert außer 1 ab.
  Determinismus kommt über `strict: True` und klare Prompts.
- **`api_version` aus `settings`**, nie hardcoden — Fantasie-Strings
  wie `"2024-10-21-preview"` führen zu HTTP 404.

## Pflicht-Regel für DB-Inserts

- **`run.db.insert_row(table, dict)` statt handgeschriebenem
  `INSERT INTO ... VALUES (?, ?, ...)`** — ein Komma zu wenig,
  Spaltenreihenfolge falsch, und Du hast `17 values for 18 columns`
  (UAT-Bug #6 Ursprung). `insert_row` validiert Schema, quotet
  Sonderzeichen automatisch und kann `on_conflict="update:col"`
  als Einzeiler-Upsert.

## Prüf-Checkliste vor Flow-Start

- [ ] Imports aus `azure.ai.documentintelligence` bzw. `openai`,
      **nicht** aus `disco.services.*`.
- [ ] `begin_analyze_document` bekommt `body=<bytes>`, nicht
      `content=` / `document=` / `file=`.
- [ ] `content_type="application/pdf"` gesetzt, wenn `body` bytes
      ist.
- [ ] `response_format={"type": "json_schema", ...}` bei LLM-
      Klassifikation.
- [ ] Credentials aus `settings.*`, nicht raw `os.getenv`.
- [ ] Fehlerpfad wirft `RuntimeError`, kein weicher
      `try/except`-Fallback.
- [ ] **Nach jedem LLM-Call `run.add_cost_from_azure_response(response)`** —
      sonst zeigt das UI `0 EUR` (UAT-Bug #10).
- [ ] **Für INSERTs in `agent_*`-Tabellen `run.db.insert_row(table, dict)`** —
      keine handgezählten Tupel mehr (UAT-Bug #6 Ursprung).
