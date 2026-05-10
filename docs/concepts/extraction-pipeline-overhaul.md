# ★ EXTRACTION-PIPELINE OVERHAUL — Konsolidiertes Konzept

**Status:** Phase 1+2 in Umsetzung 2026-04-30, Phase 6 (Failed vs Pending) offen.
**Notion-BL-Item:** verlinkt aus dem Disco-Backlog (Component: Pipeline / Extraction).


Konsolidiert die folgenden Backlog-Eintraege in EIN Konzept:
- "Pipeline-Vollstaendigkeits-Sicht" (Zeile ~980)
- "Office-Formate in die Extraction-Pipeline" (~1056)
- "Extraction nur auf kanonische Dateien" (~1094)
- "Anhaltspunkte fuer replaces / format-conversion-of" (~1338) — Stufe 1+2
- "Stabilitaets-Bugs aus FTS5-Deadlock" Section 2+3 (Counter + max_retries)
- "Extraction-Pipeline-UX: Ampelsystem, Auto-Pipeline, Batch-Mode" (~1858)
- "File-Internal-Metadata bei Registrierung extrahieren" (~2057)

Alte Eintraege bleiben als Vertiefung stehen, der Konsolidations-Eintrag
hier ist die Plan-Quelle.

### Konzept

**6 Pipeline-Schritte** mit Step-Aggregat-Ampel in der Sidebar:

| # | Schritt | DB-Quelle | Status |
|---|---|---|---|
| 1 | Registrierung (inkl. File-Internal-Metadata) | `agent_sources` | 🟢/🟡/🔴 |
| 2 | Externe Anreicherung (Begleit-Excel + SharePoint) | `agent_source_metadata`, `agent_sharepoint_docs` | 🟢/🟡/🔴/⚪ (n.a.) |
| 3 | Kanonik (Duplikate, Replaces, Format-Konversionen) | `agent_source_relations` | 🟢/🟡/🔴 |
| 4 | Routing | `work_extraction_routing` | 🟢/🟡/🔴 |
| 5 | Extraction | `agent_doc_markdown` | 🟢/🟡/🔴 |
| 6 | Suchindex | `agent_search_docs` | 🟢/🟡/🔴 |

**Status-Definition:**
- 🟢 alle done, 0 failed, 0 pending
- 🟡 alle abgehakt (done + failed = total), aber failed > 0
- 🔴 pending > 0 (Files warten auf Verarbeitung)
- ⚪ Schritt n.a. (z.B. Anreicherung wenn keine externe Quelle)

### User-Entscheidungen (2026-04-30)

1. **State-Berechnung**: SQL-View, live aus den 4 Tabellen abgeleitet
   (drift-frei, kein Sync-Code in jedem Pipeline-Schritt noetig).
   Wenn bei 5000+ Files Performance-Problem → spaeter persistierte
   Spalte als V2.

2. **Auto-Pipeline-Default**: NEIN. Pipeline laeuft nicht automatisch
   durch. ABER: Disco soll proaktiv anbieten *"Soll ich den ganzen
   Pipeline-Durchlauf machen?"* nach `sources_register`. Plus
   einzelne Schritte wiederholbar mit ggf. anderer Config — nicht zu
   kompliziert designen.

3. **State-Erzwingung**: Pragmatisch. Tools warnen im Result wenn
   Vorbedingung nicht erfuellt, lassen aber durch (kein Hard-Block).
   System-Prompt-Regel fuer Disco's Verhalten.

4. **File-Status pro Datei in Explorer-Spalte**: Phase 2, jetzt nicht.
   Phase 1 = Step-Aggregat in Sidebar reicht.

### UI-Vorschlag

Expandable Section unter `FLOWS` in der Sidebar:

```
▼ PIPELINE-STATUS                  ↻
  🟢  1. Registrierung        1837 / 1837
  ⚪  2. Externe Anreicherung  n.a.
  🟢  3. Kanonik              1708 → 1517 kanonisch
  🔴  4. Routing                 0 / 1517
  🔴  5. Extraction              0 / 1517
  🔴  6. Suchindex               0 / 1517
```

**Klick auf Schritt:**
- 🔴 → Modal "X Files warten. Jetzt anstossen?" mit Cost-Schaetzung +
       Buttons `[Test mit limit=10] [Full-Run]`
- 🟡 → Detail-Liste der failed Files (Phase 2)
- 🟢/⚪ → kein Effekt oder Statistik-Popup

### n_total-Maßstab pro Schritt

- Schritt 1-3: alle aktiven sources
- Ab Schritt 4 (Routing): nur kanonische Files (Disco extrahiert nie
  Duplikate/Replaces)

### Migrierbarkeit

- View-Migration ist trivial: `CREATE VIEW IF NOT EXISTS v_pipeline_status`
- Keine Schema-Aenderung an Bestand-Tabellen
- Bei Bedarf View droppen + neu anlegen, kein Datenverlust
- Idempotent
- Bestandsprojekte (campus-reuter, lager-halle, rea-denox) profitieren
  sofort: View liest live aus existierenden Tabellen

### Implementierungs-Phasen

**Phase 1 (heute) — View + Sidebar-UI + manueller Trigger**
- Migration 010 datastore: `v_pipeline_status` View
- Backend-Endpoint `GET /api/projects/{slug}/pipeline-status`
- Frontend: neue Sidebar-Section unter Flows, mit Polling-Refresh
- Klick-Modal mit Cost-Schaetzung + Test/Full-Buttons
- System-Prompt-Regel (1-2 Zeilen): proaktiv nach `sources_register`
  fragen ob ganzer Durchlauf

**Phase 2 (spaeter) — File-Internal-Metadata + Office-Formate**
- DOCX/PPTX-Engines (eigener Backlog-Eintrag, jetzt zugeordnet)
- File-Internal-Metadata-Extraktor (`disco/sources/file_metadata.py`)
- Schema-Erweiterung `agent_sources` mit den 7 first-class-Spalten
- Backfill-Script fuer Bestand
- View beruecksichtigt das ggf. fuer Schritt 1-Detail

**Phase 3 (spaeter) — Retry-Strategie + Failed-Markierung**
- max_retries=3 mit Exponential-Backoff
- `extraction_failed`-State in agent_sources
- Skip beim Re-Run, force_retry_failed=true als Override
- LibreDWG-Permanent-Fail-Detection (siehe Backlog FTS5-Deadlock S.4)

**Phase 4 (spaeter) — Counter-Konsistenz-Bugfixes**
- Stale-Run-Detection beim Service-Start
- Counter-Update-Bug nach Crash (workspace.db WAL-Recovery)

**Phase 5 (spaeter) — File-Status-Pille im Explorer**
- Pro Datei eine Status-Pille (Datei-Ebene zusaetzlich zum Step-Aggregat)

User-Quote (2026-04-30): *"Ich haette das ampelsystem aber gerne
praktisch auf extraction pipeline step ebene. Eine art process ampel
fuer jeden prozessschritt."*

### Phase 6 (Pipeline-Status-Schaerfung) — Failed vs Pending offen

Offen (Phase B):
- ❌ **Failed vs Pending in Schritt 4 + 5.** `work_extraction_routing`
  und `agent_doc_markdown` haben keine error-Spalte. Failed
  Routings/Extractions tauchen einfach nicht auf → werden als pending
  (rot) gezaehlt. Nur Schritt 6 (Suchindex) kann ehrlich gelb werden.
  Erfordert Schema-Migration (error TEXT + retry_count INTEGER) und
  Code-Aenderungen in beiden Flows zum Befuellen. Damit dann auch
  🟡 in Schritt 4 + 5 moeglich.
