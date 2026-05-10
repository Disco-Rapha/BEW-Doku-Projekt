# Architektur-Entscheidungen — Disco

Dieses Dokument hält bewusste Architektur-Entscheidungen fest, die nicht
direkt aus dem Code ablesbar sind. Wenn ein Beobachter später fragt
„warum macht Disco das so / warum ist X **nicht** drin?", findet er hier
die Begründung.

Format pro Eintrag: kurzer Titel, Datum, Status (aktiv / überholt),
Kontext, Entscheidung, Konsequenzen.

---

## 2026-05-07 — context-Excel-Default zu Markdown gewechselt

**Status:** aktiv

### Kontext

Bisher routete `extraction_routing_decision` für context-Excels
automatisch die `excel-table-import`-Engine — das schreibt Excel-
Sheets direkt als SQL-Tabellen `context_<slug>` in `workspace.db`.
sources-Excels gingen via `excel-openpyxl` zu Markdown.

Folge in der Praxis: **60+ `context_*`-Tabellen pro Projekt**
(z.B. rea-denox aus VGB-S-811-Imports), viele davon ungenutzt.
Wildwuchs in `workspace.db`, Sidebar unübersichtlich, Disco
verlor Übersicht über die Lookup-Strukturen, Search-Index nicht
über Excel-Inhalte konsultiert.

### Entscheidung

Default-Routing für context-Excels auf `excel-openpyxl` (Markdown)
umstellen. SQL-Tabellen-Import ist **bewusste User-Aktion** via
`import_xlsx_to_table`, nicht mehr automatischer Pipeline-Schritt.

### Was sich ändert

- `disco/docs/routing.py:_decide_excel` ignoriert `file_role` und
  liefert immer `excel-openpyxl`.
- Migration `workspace/006_excel_context_remigrate.sql` löscht
  bestehende Routings mit `engine='excel-table-import'` — beim
  nächsten `extraction_routing_decision`-Lauf werden die Files
  neu klassifiziert (zu `excel-openpyxl`), beim folgenden
  `extraction`-Lauf zu Markdown extrahiert.
- `context-onboarding`-Skill: Default-Verhalten dokumentiert,
  SQL-Import als bewusster Pfad markiert.
- System-Prompt: kompakter Hinweis ergänzt.

### Was bleibt

- Bestehende `context_*`-Tabellen in Prod-Workspaces bleiben
  unverändert (nicht-destruktiv). Wenn der User sicher ist, dass
  ein Markdown-Pendant da ist und nichts mehr dagegen joint, kann
  er einzelne droppen.
- `import_xlsx_to_table`-Tool bleibt erhalten — wird über Skill
  `excel-formatter` getriggert.
- `excel-table-import`-Engine als Code bleibt erhalten — Tabellen-
  Imports sind weiterhin möglich, nur eben nicht automatisch.

### Konsequenzen

- Pipeline-Ampel zeigt nach Migration die zugehörigen Files in
  Schritt 4+5+6 als pending → User sieht gezielt, welche context-
  Excels noch kein Markdown haben, und kann Cleanup gezielt
  ansteuern.
- Search-Index-Coverage für context-Inhalte vollständig.
- workspace.db-Wildwuchs gestoppt.
- Bei Lookup-Tabellen-Bedarf etwas mehr Disziplin — User muss
  bewusst sagen *„importier mir die KKS-Liste"*, statt dass das
  automatisch passiert.

### Wann zurück?

Falls der manuelle SQL-Import-Pfad zu mühsam wird (z.B. weil bei
jedem Projekt 3–5 Standard-Lookups gefragt sind), könnten wir einen
**Lookup-Hinweis-Mechanismus** einbauen: ein Marker-File
`context/_lookup_tables.txt` listet pro Excel den gewünschten
SQL-Import-Modus, der `excel-openpyxl`-Pfad respektiert das.
Aktuell zu früh — abwarten, ob der manuelle Pfad reicht.

---

## 2026-05-06 — docling als PDF-Engine entfernt

**Status:** aktiv

### Kontext

Disco hatte drei PDF-Engines:
- `pdf-azure-di` (Cloud, Default für Standard-PDFs)
- `pdf-azure-di-hr` (Cloud, für Pläne/Großbilder, höher aufgelöst)
- `pdf-docling-standard` (lokal, DocLayNet + TableFormer + EasyOCR auf MPS)

In der Praxis (rea-denox, lager-halle, campus-reuter) wurde
`pdf-docling-standard` über 30+ Tage **0× von Routing oder User
gewählt**. Default-Routing (`disco/docs/routing.py`) ging seit dem
Bench-Entscheid 2026-04-25 sowieso immer auf `pdf-azure-di`, weil
docling auf ~4 % der Text-PDFs halluzinierte.

Gleichzeitig zog docling **schwere Kosten** mit:
- `docling>=2.90.0`-Dependency (mit transitiven HF/torch-Paketen)
- `~/.cache/huggingface/`-Setup-Anforderung beim ersten Lauf
- `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` / `HF_DATASETS_OFFLINE`-
  Flags in `config.py` + `flows/service.py` als Defence-in-Depth
- Setup-Fallstrick „frische Maschine ohne Cache → docling kann nicht
  laden" — Backlog-Eintrag H10
- ~120 SLOC docling-spezifischer Code in `disco/pdf/markdown.py`

### Entscheidung

docling komplett aus dem Codebase entfernen. PDF-Pipeline reduziert
auf zwei Azure-DI-Engines.

### Was raus ist

- `docling>=2.90.0` aus `pyproject.toml`
- `_extract_docling_standard()` aus `src/disco/pdf/markdown.py`
- `pdf-docling-standard` aus `ENGINES_BY_KIND` (`disco/docs/__init__.py`)
- `_LEGACY_ENGINE_MAP` Eintrag in `disco/docs/pdf.py`
- HF-Offline-Flags + `_apply_offline_env`-Helper in `disco/config.py`
- `child_env.setdefault("HF_HUB_OFFLINE", ...)` etc. in
  `disco/flows/service.py`
- docling-Erwähnungen in `system_prompt.md` + Flow-READMEs

### Was bleibt

- Bestandsdaten in `agent_doc_markdown` mit `engine='docling-standard'`
  bleiben unverändert (read-only history). Schema-Spalte `engine` ist
  TEXT, kein CHECK-Constraint, also bleiben alte Werte gültig
  abrufbar; nur neue Routing-Decisions können den Wert nicht mehr
  setzen.
- `disco/pdf/`-Modul bleibt — beherbergt jetzt nur noch die
  Azure-DI-Engines.

### Wann zurück?

Falls Disco später eine vollständig **lokale PDF-Pipeline** braucht
(Offline-Anwendung, Datenschutz-Anforderung, Cloud-Cost-Cap), kann
docling über `git log -- src/disco/pdf/markdown.py` zurückgeholt
werden. Empfohlen wäre dann eine Mess-Session mit echten Dokumenten,
um die 4 %-Halluzinations-Rate gegen das aktuelle Modell-Niveau neu
zu bewerten — die Bench-Entscheidung 2026-04-25 ist von einem
älteren docling-Modellstand.

### Konsequenzen

- Disco kann **nur noch über die Cloud** PDFs extrahieren. Bei
  Foundry-Outage oder Sweden-Central-Quota-Limit gibt es keinen
  Fallback.
- Setup ist deutlich einfacher: keine 800 MB+ HF-Modell-Downloads
  beim ersten Lauf, keine MPS-/Apple-Silicon-spezifischen
  Dependencies.
- BACKLOG-Eintrag H10 (Setup-Fallstrick mit HF-Cache) wird obsolet.

---

## 2026-05-09 — Memory-Reform: 3-Schichten-Modell mit Marker, Kapitel-Lookup, Schicht-3 in `agent_table_docs`

**Status:** aktiv, deployed dev (`disco-dev-agent v38`) + prod (`disco-prod-agent v50`).

### Kontext

Das alte Memory-System hatte ein einziges, frei wachsendes `DISCO.md`
pro Projekt — Default-`memory_read` lieferte einen 8-KB-Cap auf den
Anfang der Datei. In Prod-Projekten mit ~1.800 Dateien war DISCO.md
bis 56 KB groß (lager-halle), enthielt 40+ chronologische H2-Sektionen
und mehrfach denselben Header (`## Entscheidungen` 4×, `## SharePoint-Links` 3×).
Konsequenz: bei jeder Disco-Session wurden 8 KB unsortierter Inhalt
geladen — viele Tokens, wenig zielgenaues Wissen.

### Entscheidung

**Drei explizite Schichten:**

1. **Schicht 1** in DISCO.md über dem Marker `<!-- DISCO-LAYER-1-END -->`
   (max 3,5 KB): Identität, Aktueller Fokus, Konventionen, Lookup-Pfade.
   Wird beim Default-`memory_read` automatisch geladen, plus ein
   automatisch erzeugter Kapitel-Index der Schicht 2.
2. **Schicht 2** unter dem Marker: themenbezogene Wissens-Kapitel
   mit `<!-- chapter-meta: tags/created/status -->`-Block. Wird nur per
   `memory_read({chapter: "..."})` geladen — exakter, Substring-, Tag-
   und Body-Match in dieser Reihenfolge. Side-Effect: `last_referenced`
   und `reference_count` im Meta-Block werden automatisch aktualisiert.
3. **Schicht 3** in `agent_table_docs` (Tabelle in workspace.db,
   Migration `008_agent_table_docs.sql`): pro Projekt-Tabelle eine
   kurze Beschreibung + Schema-Summary + Beispiel-Query + Quell-Files.
   Tools `table_doc_set` / `table_doc_get`. Tabellen-Wissen lebt
   **nicht** in DISCO.md.

**Trace-Log** unter `.disco/memory-access.log` (TSV) protokolliert
jeden `memory_read`-Aufruf mit Modus, Datei, Hit/Miss, Bytes — Basis
für spätere Aufräum-Entscheidungen.

**NOTES-Auto-Archivierung** in der Compaction: Einträge älter als
30 Tage wandern nach `.disco/notes-archive/YYYY-MM.md`, idempotent.

### Backward-Compatibility

Projekte ohne Marker fallen automatisch auf den Legacy-8-KB-Cap zurück.
Kein Migrationszwang. Migration auf das Schichten-Format kann pro
Projekt einzeln erfolgen (Backup, Schicht-1-Trim, Kapitel mit
chapter-meta neu strukturieren). Die drei Prod-Projekte
(rea-denox, campus-reuter, lager-halle) wurden am 2026-05-09
migriert — DISCO.md schrumpfte von 14 KB / 5,7 KB / 56 KB
jeweils auf < 35 KB mit ≤ 3,5 KB Schicht 1.

### Konsequenzen

- **Token-Sockel pro Onboarding** ~67 % kleiner (8 KB → ~2,6 KB
  inkl. README + NOTES-Tail).
- **Gezielte Folgefragen** holen ~1–1,7 KB statt 8 KB, gemessen auf
  rea-denox + campus-reuter live.
- **Tabellen-Wissen ist projektübergreifend einheitlich** durchsuchbar
  (eine SQL-Tabelle statt verstreuter DISCO.md-Sektionen).
- **Trace-Log** macht ungenutzte Kapitel sichtbar — Grundlage für
  spätere Pflege.

### Pointer

- Konzeptdokument im Archiv:
  `docs/archive/memory-reform-2026-05-09.md`.
- E2E-Validierung: `tests/e2e/scenarios/03-memory-reform.md`
  (Disco-Mind-Test T1–T7).
- Code: `src/disco/agent/functions/memory.py`,
  `src/disco/agent/functions/table_docs.py`,
  `src/disco/chat/compaction.py`.

---

## 2026-05-10 — Shadow-Architecture für Disco-Erweiterungen + Append-only-Evidence-Pattern

**Status:** aktiv, gilt fuer alle anstehenden Reasoning-Layer-Erweiterungen
(Hybrid-Search/RAG, Embedding-DCC-Klassifikator, Object-Graph).

### Kontext

Disco hat heute drei produktive Reasoning-Schichten — Sources/Pipeline,
DCC-/Metadaten-Klassifikation, Memory mit 3-Schichten-Modell — die in
den drei Prod-Projekten taeglich genutzt werden. Mehrere geplante
Erweiterungen (Hybrid-Search, Embedding-Klassifikator, Object-Graph)
wuerden klassisch als **Refactoring** der bestehenden Tabellen
implementiert: alte Schemata umziehen, neue Pflege-Workflows einfuehren,
Risiko fuer den laufenden Betrieb.

User-Beobachtung 2026-05-10: *„Man kann das als eigene Layer bauen,
ohne dass die aktuelle bereits sehr gut funktionierende Struktur
beeintraechtigt wird. Sobald Disco dann die Analyse-Tools ueber die
Graph-DB und RAG bekommt, kann man sehen, ob die Ergebnisse besser
werden."*

### Entscheidung

Alle Reasoning-Layer-Erweiterungen werden als **additive Schichten
neben der bestehenden Architektur** implementiert. Die alten Tabellen
und Tools bleiben unangetastet, neue Tabellen und Tools laufen
parallel. Disco kann pro Tool-Aufruf entscheiden, welche Schicht er
nutzt — alt, neu, oder beide vergleichend.

Pattern in Stichworten:

```
   ┌──────────────────────────────────────────────┐
   │ Disco-Tool-Layer                             │
   │ alte Tools (sqlite_query, search_index, …)   │
   │ neue Tools (hybrid_search, object_show, …)   │
   └──────────────────────────────────────────────┘
       │
       ├──► Layer Alt (unangetastet, läuft weiter)
       │      agent_sources, agent_doc_markdown,
       │      agent_kks_master_current, agent_dcc_prediction,
       │      agent_component_register, agent_building_element_*
       │
       └──► Layer Neu (parallel, additiv)
              agent_search_chunks (Embeddings)
              agent_dcc_prediction (mit predictor_version)
              agent_objects, agent_object_relations,
              agent_object_property_evidence,
              agent_object_document_links
```

### Pattern-Variante: Append-only Evidence + Current-State-View

Innerhalb der neuen Schichten gilt fuer alle Reasoning-Daten ein
**zweites Pattern**: Evidence wird nie gelöscht, nur Status geändert.
Aktueller Wahrheitsstand kommt aus einer abgeleiteten View über
status='confirmed' / 'active'.

Die Tabellen-Familie pro Reasoning-Domaene:

- **Current-State-Tabelle** (z. B. `agent_objects`) — schnelle Queries,
  enthält den aktuell konsolidierten Wahrheitsstand
- **Versions-Tabelle** (z. B. `agent_object_versions`) — Append-only
  Snapshot-JSON pro Aenderung, mit `change_type` und `changed_by`
- **Evidence-Tabelle** (z. B. `agent_object_property_evidence`) —
  Append-only Roh-Belege, mit `status` aus
  `'suggested'` | `'confirmed'` | `'rejected'` | `'superseded'` und
  `superseded_by` als self-FK
- **Scan-Tabelle** (z. B. `agent_object_scans`) — Audit-Log pro
  Befuellungs-Batch mit Counts (added/changed/retired/rejected)
- **View** auf den aktuellen Wahrheitsstand fuer Tool-Queries

### Disco-Vorlaeufer

Das Pattern ist nicht neu — Disco hat es schon zweimal:

- `agent_sources` + `agent_source_scans` mit Hash-Delta-Detection
  (Sources werden nicht geloescht, nur als ersetzt/abgelaufen markiert)
- `agent_kks_evidence` / `_review` mit `evidence_kind` + `confidence`
  (Multi-Source-Belege pro KKS, mit Quellen-Provenienz)
- Memory-Reform 2026-05-09 mit chapter-meta-Side-Effects
  (`last_referenced` + `reference_count` als implizite Lebenszyklus-
  Achse)

Die Erweiterung auf Object-Graph + RAG ist **keine neue DNA**, sondern
dasselbe Pattern auf einer neuen Reasoning-Ebene.

### Konsequenzen

**Plus:**
- Nullrisiko fuer die laufenden Prod-Projekte. Bestehende Workflows
  bleiben unberuehrt.
- A/B-Vergleichbarkeit zwischen alter und neuer Schicht. Wir koennen
  messen, ob die neue Schicht wirklich besser ist, statt zu spekulieren.
- Rollback ist trivial — wenn eine neue Schicht nicht haelt, Tools
  nicht mehr nutzen, Daten bleiben fuer Audit.
- Lebenszyklus eines Projekts ist nativ abbildbar (Objekte werden
  pensioniert, Properties werden korrigiert, Relations werden
  retiriert).
- Kompatibel mit RL9910-A03-Audit-Anforderungen (Spurenlesbarkeit
  jeder Aenderung).

**Minus:**
- Mehr Storage (alte und neue Schicht parallel). In SQLite akzeptabel.
- Sync-Workflows zwischen alt und neu (z. B. Korrekturen aus alter
  Welt in neue Welt nachziehen). Werden als kleine Pflege-Flows
  implementiert.
- Tool-Gateway-Frage: welcher Tool-Aufruf nutzt welche Welt? Loesung
  per Skill-Trigger und expliziter Tool-Auswahl.

### Roadmap

Die drei naechsten grossen Reasoning-Erweiterungen werden alle nach
diesem Muster umgesetzt:

1. **Phase 1 — Hybrid-Search/RAG** (additiv: `agent_search_chunks` mit
   Embedding-Spalte neben FTS5)
2. **Phase 2 — Embedding-DCC-Klassifikator** (additiv: zweite Predictions
   in `agent_dcc_prediction` mit `predictor_version='embed_v1'`)
3. **Phase 3 — Object-Graph** (eigene neue Tabellen-Familie:
   `agent_objects`, `agent_object_versions`,
   `agent_object_property_evidence`, `agent_object_relations`,
   `agent_object_scans`)

Reihenfolge ist nicht beliebig: Phase 1 hilft beim Bootstrap von
Phase 2 und Phase 3 (Hybrid-Search als Vorfilter beim Property-Scan
und Link-Scan in Phase 3). Phase 3 wiederum verbessert spaeter Phase 1
(Object-Type-Kontext als Re-Ranking-Feature).

### Pointer

- Vorbereitungs-MD Object-Graph (ausserhalb Repo wegen Kunden-Beispielen):
  `~/Claude/discussion-prep-object-graph.md`
- BACKLOG-Eintrag: `docs/BACKLOG.md` Section *Architektur* →
  „★ Object-Graph als zweite Disco-DB"
- BACKLOG-Eintrag: `docs/BACKLOG.md` Section *Document Intelligence* →
  „IDEE: DCC-Klassifikation per Embedding-Klassifikator"
