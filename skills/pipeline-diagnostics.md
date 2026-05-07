---
name: pipeline-diagnostics
description: Diagnose des Pipeline-Status pro Datei. Antwortet "warum wurde X nicht extrahiert", "ist Y im Suchindex", "hat Z gefailt", erklärt Failure-Modi und führt einzelne Files durch alle Pipeline-Schritte.
when_to_use: Bei Pipeline-Fragen zu einzelnen Dateien (registriert, geroutet, extrahiert, indiziert), bei Fehler-Diagnose, beim Ziel "diese Datei durch die ganze Pipeline schicken", bei "warum funktioniert X nicht".
---

# Skill: pipeline-diagnostics

Disco hat eine 6-Schritt-Pipeline (Registrierung → Externe Anreicherung
→ Kanonik → Routing → Extraction → Suchindex). Dieser Skill hilft Dir
zu diagnostizieren, **wo eine einzelne Datei in der Pipeline steht**,
warum sie ggf. hängt, und wie Du sie weiter treibst.

## Status-Vokabular pro Schritt

| Code | Bedeutung |
|---|---|
| `done` | Schritt erfolgreich abgeschlossen |
| `pending` | Vorbedingung erfüllt, Schritt noch nicht ausgeführt |
| `failed` | Versuch lief, ist mit Fehler geendet |
| `done_empty` | Schritt lief, Output war leer (z.B. PDF ohne Text) |
| `skipped_unsupported` | Format/Datei kann diesen Schritt nicht durchlaufen (kein Engine-Mapping) |
| `skipped_upstream` | Vorgänger-Schritt hat den File schon ausgeschlossen (Duplikat, Replace, etc.) |
| `na` | Schritt nicht anwendbar (z.B. keine externe Quelle vorhanden) |

## Per-Schritt-Diagnose

### Schritt 1 — Registrierung

**Frage:** Ist die Datei in `agent_sources` mit `status='active'` eingetragen?

```sql
SELECT id, kind, rel_path, status, sha256
FROM ds.agent_sources
WHERE rel_path LIKE '%dateiname%';
```

| Befund | Aktion |
|---|---|
| Eintrag existiert mit `status='active'` | ✅ done — weiter zu Schritt 2 |
| Kein Eintrag, Datei aber im FS | `pending` — `sources_register` laufen lassen |
| Eintrag mit `status='deleted'` | Datei wurde im FS gelöscht. Wenn sie wieder da ist, neu registrieren. |
| Pfad-Part hat `_` oder `.` Prefix | `skipped_unsupported` — Konvention: `_meta/`, `_manifest.md`, `.DS_Store` etc. werden nie registriert |

### Schritt 2 — Externe Anreicherung

**Frage:** Hat die Datei einen Eintrag in `agent_source_metadata` (Begleit-Excel) oder `agent_sharepoint_docs`?

```sql
-- Begleit-Excel-Metadata?
SELECT COUNT(*) FROM ds.agent_source_metadata
WHERE source_id = (SELECT id FROM ds.agent_sources WHERE rel_path = ?);
```

| Befund | Aktion |
|---|---|
| Eintrag vorhanden | ✅ done |
| Keine externe Quelle existiert (kein Begleit-Excel, kein SP) | `na` — Schritt entfällt, ⚪ grau in Ampel |
| Externe Quelle existiert, aber dieser File nicht enthalten | `pending` — `sources_attach_metadata` mit passendem Mapping aufrufen |

### Schritt 3 — Kanonik

**Frage:** Hat die Datei eine `duplicate-of`-Relation als `from_source_id`?

```sql
SELECT r.kind, r.to_source_id, s2.rel_path AS canonical_path
FROM ds.agent_source_relations r
JOIN ds.agent_sources s2 ON s2.id = r.to_source_id
WHERE r.from_source_id = (SELECT id FROM ds.agent_sources WHERE rel_path = ?);
```

| Befund | Aktion |
|---|---|
| Keine Relation als from-Seite | `canonical` — Datei wird durch Pipeline gepusht |
| `kind='duplicate-of'` | `skipped_upstream` — kanonisches Original (siehe `to_source_id`) wird verarbeitet |
| `kind='replaces'` als from | `skipped_upstream` — durch neuere Version ersetzt |

### Schritt 4 — Routing

**Frage:** Hat `work_extraction_routing` einen Eintrag mit `engine` befüllt?

```sql
SELECT engine, reason, error, retry_count
FROM work_extraction_routing
WHERE file_id = (SELECT id FROM ds.agent_sources WHERE rel_path = ?);
```

| Befund | Aktion |
|---|---|
| `engine` not null, `error` IS NULL | ✅ done — weiter zu Schritt 5 |
| `engine` IS NULL/'', `error` IS NULL | `skipped_unsupported` — Format hat keine Engine. Office-Engine ergänzen oder Datei akzeptieren als nicht-extrahierbar |
| `error` IS NOT NULL | `failed` — siehe Failure-Routing-Tabelle unten |
| Kein Eintrag | `pending` — `flow_run extraction_routing_decision` laufen lassen (auf Bulk oder mit `only_file_ids=[<id>]`) |

### Schritt 5 — Extraction

**Frage:** Hat `agent_doc_markdown` einen Eintrag mit `error IS NULL` und `char_count > 0`?

```sql
SELECT engine, char_count, error, retry_count, length(md_content) AS md_len
FROM ds.agent_doc_markdown
WHERE file_id = (SELECT id FROM ds.agent_sources WHERE rel_path = ?);
```

| Befund | Aktion |
|---|---|
| Eintrag, `error IS NULL`, `char_count > 0` | ✅ done |
| Eintrag, `error IS NULL`, `char_count = 0` | `done_empty` — Datei lief durch, kein Text-Inhalt (Scan-PDF ohne OCR-Treffer, leere Excel, leere DWG) |
| Eintrag, `error IS NOT NULL` | `failed` — siehe Failure-Routing-Tabelle |
| Kein Eintrag, `engine` aus Schritt 4 not null | `pending` — `flow_run extraction` laufen lassen |
| Schritt 4 war `skipped_unsupported` oder `failed` | `skipped_upstream` — Schritt 4 zuerst klären |

### Schritt 6 — Suchindex

**Frage:** Hat `agent_search_docs` einen Eintrag mit `error IS NULL`?

```sql
SELECT n_chunks, indexed_at, error
FROM ds.agent_search_docs
WHERE rel_path = (SELECT 'sources/' || rel_path FROM ds.agent_sources WHERE rel_path = ?);
```

| Befund | Aktion |
|---|---|
| Eintrag, `error IS NULL` | ✅ done |
| Eintrag, `error IS NOT NULL` | `failed` — error-Text analysieren, Engine wechseln, retry |
| Kein Eintrag, Schritt 5 war done | `pending` — `build_search_index` aufrufen |
| Schritt 5 war `done_empty`, `failed`, oder `skipped_*` | `skipped_upstream` — kein Inhalt zum Indizieren |

## Failure-Routing-Tabelle

| Failure-Pattern | Was tun |
|---|---|
| `Azure DI 5xx` (transient) | retry max 3×, dann als permanent-failed markieren, User informieren |
| `Azure DI 429` (Quota) | warten und retry; wenn anhaltend, parallel laufende Flows reduzieren |
| `libredwg SIGABRT` | als permanent-failed markieren, in NOTES.md eintragen, **NICHT** erneut versuchen (DWG ist korrupt) |
| `openpyxl "Invalid file"` | retry mit alternativer Engine wenn verfügbar (z.B. `import_xlsx_to_table` als Workaround) |
| `OOM` / Memory-Error | mit `only_file_ids=[<id>]` und kleinerem Batch retry |
| `FileNotFoundError` | Datei wurde im FS gelöscht. `sources_register` neu laufen lassen — Eintrag wird auf `status='deleted'` gesetzt |
| `Unknown engine: …` | Routing-Tabelle hat einen veralteten Engine-Wert. Routing-Eintrag löschen, neu routen lassen |

## Reparatur-Workflows

### Eine einzelne Datei durch die ganze Pipeline schicken

```text
# 1. Status prüfen
pipeline_file_status({"rel_path": "sources/Elektro/foo.pdf"})

# 2. Ggf. registrieren (falls Schritt 1 pending)
sources_register({"scope": "sources"})

# 3. Routing für nur diese Datei (sobald per-File-Trigger da ist, sonst Bulk)
flow_run({
  "flow_name": "extraction_routing_decision",
  "config": {"only_file_ids": [<id>]}
})

# 4. Extraction
flow_run({
  "flow_name": "extraction",
  "config": {"only_file_ids": [<id>]}
})

# 5. Suchindex
build_search_index({"paths": ["sources/Elektro/foo.pdf"]})

# 6. Verifizieren
pipeline_file_status({"rel_path": "sources/Elektro/foo.pdf"})
```

### Failed-Datei reparieren

```text
# 1. Diagnose
pipeline_file_status({"rel_path": "..."})
# → liefert error-Text + retry_count + welcher Schritt gescheitert

# 2. Failure-Routing-Tabelle konsultieren

# 3. Aktion
# - bei transient: erneut triggern (siehe oben)
# - bei permanent: in NOTES.md eintragen, akzeptieren

# 4. Bei "permanent": work_extraction_routing oder agent_doc_markdown
#    löschen für diese Datei, dann re-run mit alternativer Engine
sqlite_write("DELETE FROM work_extraction_routing WHERE file_id = ?")
```

### Re-Routing einer Datei (z.B. nach Engine-Wechsel)

```text
# Routing-Eintrag löschen → file fällt auf "Schritt 4 pending" zurück
sqlite_write("DELETE FROM work_extraction_routing WHERE file_id = ?")

# Routing neu starten — file wird mit aktueller Default-Logik klassifiziert
flow_run({"flow_name": "extraction_routing_decision",
          "config": {"only_file_ids": [<id>]}})

# Wenn neue Engine: extraction-Eintrag auch droppen
sqlite_write("DELETE FROM ds.agent_doc_markdown WHERE file_id = ?")
flow_run({"flow_name": "extraction", "config": {"only_file_ids": [<id>]}})
```

## Was Du dem Nutzer zeigst

Bei einer Diagnose-Frage **immer** in dieser Reihenfolge antworten:

1. **Status pro Schritt** als kompakte Tabelle (✅ / 🔴 / 🟡 / ⚪)
2. **Welcher Schritt hängt** und warum (error-Text wörtlich zitieren wenn vorhanden)
3. **Konkrete nächste Aktion** (max 1 Befehl)
4. **Erst nach User-OK ausführen** — Disco fragt nicht stillschweigend

Beispiel-Antwort:

> Datei `sources/Elektro/foo.pdf` (file_id=4711):
> - 1 Registrierung: ✅ done
> - 2 Anreicherung: ⚪ na (kein Begleit-Excel)
> - 3 Kanonik: ✅ canonical
> - 4 Routing: ✅ done (engine=pdf-azure-di-hr)
> - 5 Extraction: 🟡 failed nach 2 Versuchen (`Azure DI 503: Service Unavailable`)
> - 6 Suchindex: ⚪ skipped_upstream
>
> Failed in Schritt 5 mit transientem Azure-503. Empfehlung: einmal
> retry. Soll ich das jetzt auslösen?
