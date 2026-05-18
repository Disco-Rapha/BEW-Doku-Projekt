# ★ Data-Lineage + Daten-Architektur Ebene 3

**Status:** Konzept-Diskussion offen, prio TOP.
**Entstanden:** 2026-05-07 (konsolidiert aus zwei Themen).
**Notion-BL-Item:** verlinkt aus dem Disco-Backlog (Component: Architecture / Data-Model).

> Hinweis: Beispiele in diesem Doc nennen `work_canonical_sources` —
> seit der **Pipeline-Reform v2** (2026-05-16) ist `agent_sources`
> strukturell dedupliziert (eine Zeile pro Hash), `work_canonical_sources`
> ist als Sonder-View dadurch redundant. Konzept der Lineage selbst ist
> davon unberührt. Aktuelles datastore-Modell:
> [`pipeline-reform-v2.md`](pipeline-reform-v2.md).


**Konsolidiert 2026-05-07** — diese zwei Themen sind eng verflochten und
werden gemeinsam bearbeitet:

1. **Lineage** (woher kommen Artefakte, mit welcher Logik, wozu)
2. **Schichten-Architektur** (Ebene 1 Provenance, Ebene 2 Content, Ebene 3 Auswertung)

Disco verzettelt sich nach mehreren Arbeitsschritten in der Datenhaltung,
weil `work_*`-Tabellen ohne Lifecycle-Konzept akkumulieren und Lineage
(Source → Transform → Output) nicht zentral festgehalten ist. Nächster
Schritt: gemeinsame Konzept-Session mit User.

---

### Teil A — Data-Lineage / Tracing fuer abgeleitete Artefakte

**Idee 2026-04-27**: Jedes Artefakt, das Disco erzeugt — Tabellen,
Excel-Exports, Reports, Charts, Markdown-Zusammenfassungen — soll
fuer Disco selbst und den User **nachvollziehbar dokumentiert**
sein:

- **Wo kommen die Daten her?** (Source-Tabellen, Source-Files)
- **Mit welcher Abfrage / Logik wurden sie erzeugt?** (SQL, Python-
  Skript, ggf. Tool-Call-Sequenz)
- **Zu welchem Zweck?** (Business-Begruendung in einem Satz)

Heute hat Disco kein zentrales Lineage-Register. Eine Tabelle
`work_canonical_report` existiert, aber niemand weiss aus dem Stand
heraus: wann wurde die erstellt, mit welchem SQL, welche Sources?
Disco wuerde das Skript suchen muessen oder im Chat-History
zurueckscrollen — beides fragil.

### User-Anforderung (2026-04-27)

> "Wir bauen ein Data-tracing auf. D.h. fuer jede Tabelle, bericht
> etc die erstellt werden, soll fuer disco nachvollziehbar dokumentiert
> werden wo die daten her kommen, mit welcher Abfrage die Daten zu
> welchem Zweck erzeugt wurden."

### DB-Schema-Vorschlag

Neue Tabelle in workspace.db:

```sql
CREATE TABLE agent_data_lineage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_type   TEXT NOT NULL,    -- 'table' | 'export' | 'report' | 'chart' | 'markdown'
    artifact_name   TEXT NOT NULL,    -- 'work_canonical_report' | 'exports/Soll-Ist-2026.xlsx'
    artifact_db     TEXT,             -- 'workspace.db' | 'datastore.db' | 'fs'
    purpose         TEXT NOT NULL,    -- 1-2 Saetze, vom Erzeuger geschrieben
    sources_json    TEXT,             -- JSON-Array: [{"type":"table","name":"agent_sources"},
                                      --              {"type":"file","path":"context/vgb-s831.pdf"}]
    query_sql       TEXT,             -- ausgefuehrtes SQL (NULL fuer Python-only-Artefakte)
    code_snippet    TEXT,             -- Python-Code-Snippet wenn nicht via SQL
    n_rows          INTEGER,          -- Result-Groesse
    schema_json     TEXT,             -- Spalten der Result-Tabelle als JSON
    created_by      TEXT,             -- 'disco-agent' | 'flow:extraction:run-12' | 'user'
    chat_message_id INTEGER,          -- optional: Link zur Chat-Nachricht
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(artifact_type, artifact_name)  -- pro Artefakt der LETZTE Erzeugungs-Eintrag
);
CREATE INDEX idx_lineage_artifact ON agent_data_lineage(artifact_type, artifact_name);
CREATE INDEX idx_lineage_created  ON agent_data_lineage(created_at);
```

UNIQUE-Constraint auf `(artifact_type, artifact_name)`: pro
Artefakt **eine** Zeile, die bei Re-Erzeugung via UPSERT
ueberschrieben wird. Fuer Historie waere eine `agent_data_lineage_history`
denkbar — Phase 2.

### Wer schreibt — Hook-Punkte

1. **`sqlite_write`** (Disco-Tool fuer DDL/DML): bei `CREATE TABLE`,
   `CREATE TABLE AS SELECT`, `INSERT INTO ... SELECT` automatisch
   einen Lineage-Eintrag schreiben. Sources werden aus dem
   geparsten SQL extrahiert (FROM-/JOIN-Tabellen). Purpose muss
   als Pflichtparameter mitgegeben werden ("Warum schreibst du
   diese Tabelle?").

2. **`build_xlsx_from_tables`** (Excel-Export): bei jedem Export
   einen Eintrag mit den Source-Tabellen, ausgefuehrtem
   Multi-Sheet-Spec und Purpose.

3. **`import_xlsx_to_table` / `import_csv_to_table`**: Eintrag
   mit Source-File-Pfad, Schema, Row-Count.

4. **`run_python`**: bei DB-Schreibungen aus dem Skript heraus —
   das Skript muss per Helper-Funktion `disco.lineage.record(...)`
   einen Eintrag schreiben. Konvention im python-executor-Skill
   verankert.

5. **Flows** (z.B. extraction): pro Run einen Eintrag fuer das
   produzierte agent_doc_markdown-Subset. Kann via
   `chat_message_id`-Feld auch verknuepfen.

### Wie Disco das nutzt

**Neues Tool `data_lineage`**:

```python
@register
def data_lineage(artifact_type: str, artifact_name: str) -> dict:
    """Lineage einer Tabelle, eines Files oder Reports. Liefert:
    - purpose, sources, query_sql/code_snippet, n_rows, schema, created_by, created_at"""
```

Bei Disco-Tool-Aufrufen wie `sqlite_query` auf einer fremden
Tabelle, koennte der Tool-Wrapper optional eine
"Lineage-Hint"-Section anhaengen ("Diese Tabelle wurde erzeugt am
... aus ... mit dem Zweck ..."), wenn das die Antwort verbessert.

System-Prompt-Erweiterung: in der Agent-Instruktion eine kurze
Regel "Wenn Du Tabellen anlegst (sqlite_write CREATE TABLE),
schreibe einen Lineage-Eintrag mit klarem Purpose".

### Use-Cases

1. **Re-Run einer Auswertung**: User fragt "kannst du den
   SOLL/IST-Report nochmal erstellen, aber gefiltert auf
   Bautechnik?". Disco liest Lineage von
   `work_canonical_report`, sieht das Original-SQL, modifiziert
   es um den Filter, fuehrt aus.
2. **Audit / Impact-Analyse**: User aendert eine Source-Tabelle.
   `data_lineage` rueckwaerts fuehrt: "welche Reports basieren
   auf agent_doc_markdown?" → 5 Tabellen + 3 Excel-Exports
   muessten neu generiert werden.
3. **Disco-Debugging**: "warum sind in dieser Tabelle nur 47
   Rows obwohl in der Quelle 1500 sind?" → Lineage zeigt das
   SQL → "ah, da war ein WHERE date > 2024 drin".
4. **Cross-Session-Continuity**: Disco kommt nach Pause zurueck
   und sieht eine `work_*`-Tabelle, die er nicht mehr im
   Kontext hat. Ueber Lineage versteht er, was sie ist und
   wofuer.

### Implementierungs-Reihenfolge

1. **Migration** workspace/006_data_lineage (oder naechste Nummer):
   Tabelle anlegen.
2. **Helper-Modul** `disco/lineage.py` mit `record(...)`-Funktion.
3. **Hook in `sqlite_write`**: parsst SQL, ruft `record(...)`. Pflicht-
   Parameter `purpose` hinzufuegen — Disco muss begruenden was er
   schreibt. Bei fehlendem Purpose: Fehler.
4. **Hook in `build_xlsx_from_tables`**, **import-Tools**: dito mit
   Pflicht-Parameter `purpose`.
5. **Tool `data_lineage`** registrieren.
6. **System-Prompt**: kurze Regel hinzufuegen "Lineage dokumentieren".
7. **UI**: Tabelle anklicken im Sidebar → Lineage-Panel mit
   Purpose, Sources, SQL, Created.

### Verbindungen zu anderen Backlog-Eintraegen

- **File-Internal-Metadata**: das ist eingebettete Source-File-
  Provenance (woher kommt das Original?). Lineage hier ist
  abgeleitete Artefakt-Provenance (was wurde DARAUS gemacht?).
  Beide ergaenzen sich.
- **Pipeline-UX (pipeline_state)**: Lineage ergaenzt das fuer
  abgeleitete Daten — pipeline_state ist pro Source, Lineage
  ist pro abgeleitetem Artefakt.
- **Cost-Tracking**: Lineage-Eintrag koennte ein `cost_eur`-Feld
  haben → "diese Tabelle hat 0.34 EUR gekostet zu erzeugen".
- **Relevance-Score**: Tabellen mit vielen Konsumenten (Lineage-
  Inverse-Lookup) sind relevanter.
- **Public-Workspace**: bei Cross-Projekt-Reuse von Tools/Skripten
  kann Lineage zeigen "dieses Skript hat in Projekt X eine Tabelle
  Y erzeugt — gleiche Logik anwendbar?".

User-Quote (2026-04-27): *"Wir bauen ein Data-tracing auf. D.h.
fuer jede Tabelle, bericht etc die erstellt werden, soll fuer
disco nachvollziehbar dokumentiert werden wo die daten her
kommen, mit welcher Abfrage die Daten zu welchem Zweck erzeugt
wurden."*


---

### Teil B — Datenverarbeitung auf Ebene 3 strukturieren

**User-Beobachtung 2026-04-27 abends**: *"Ich brauche eine Loesung
wie man die Datenverarbeitung auf Ebene 3 organisiert. Nach einigen
Arbeits- und Analyseschritten wird die Datenhaltung chaotisch und
Disco verzettelt sich mit den Daten, berechtigterweise."*

**Diskussion am 2026-04-28** — dieser Eintrag bereitet die Optionen vor.

### Problem (live in lager-halle beobachtet)

Workspace.db enthaelt heute > 80 Tabellen, viele davon Disco-erzeugte
work_*-Varianten ohne erkennbares Lifecycle-Konzept:

```
work_canonical_report
work_canonical_rsd_report
work_canonical_sources
work_extraction_routing
work_extraction_routing_backup           ← Versions-Suffix
work_extraction_routing_noncanonical
work_pdf_canonical
work_duplicate_file_ids
work_all_sources_report
work_rsd_nicht_benoetigt
work_rsd_pruefung_betrieb
agent_sp_mek_doku
agent_sp_mek_norm
agent_sp_zueblin_enddoku
agent_sp_zueblin_norm
context_armatur_regel__armatur_b_reg     ← context-Excel-Imports
context_armatur_regel__armatur_f_reg     ← x60+ aus VGB S 811
... (60+ context_*-Tabellen)
```

**Konkrete Symptome:**

1. **Versions-Chaos**: `work_extraction_routing` + `_backup` +
   `_noncanonical` — welche ist aktuell? Welche darf weg?
2. **Variant-Sprawl**: fuer jede leichte Abwandlung einer Analyse
   eine neue Tabelle (`work_canonical_*` × 3, `work_rsd_*` × 2).
3. **Kein Lifecycle**: alte Tabellen aus Voruntersuchungen
   bleiben, niemand raeumt auf.
4. **Disco verliert Ueberblick**: bei naechstem Aufruf weiss er
   nicht sicher, welche der 80 Tabellen die aktuelle Wahrheit ist.
   Re-Berechnung haeufiger als Wiederverwendung.
5. **Mental-Load fuer User**: Sidebar (selbst nach Collapsible-Fix)
   zeigt eine Wand von Namen. Was wovon abgeleitet ist, sieht man
   nur, wenn man die Skripte aus dem Chat-Verlauf rekonstruiert.

### Loesungs-Dimensionen (Diskussions-Optionen)

#### A) **Workspace-Slugs als semantische Klammer**

User definiert ein Arbeits-Set explizit: *"wir arbeiten jetzt am
SOLL/IST-Vergleich VGB S 831"*. Disco haengt allen erzeugten
Tabellen einen Slug-Praefix an:

```
work_soll_ist__canonical_sources
work_soll_ist__match_results
work_soll_ist__report
```

Vorteile: visuelle Gruppierung, einfaches Cleanup ("loesche alle
work_soll_ist__*"), Sidebar zeigt natuerliche Sub-Gruppen.

Nachteile: Naming wird laenger; User muss "Workspace" als Konzept
verstehen.

#### B) **Stages innerhalb eines Workspaces** (input → working → output)

Im Workspace gibt es drei Phasen:
- **input/**: aus DB-Quellen abgeleitete Snapshots (read-once,
  unveraenderlich nach Import)
- **working/**: Analyse-Zwischentabellen (gilt als
  wegwerfbar, Disco darf neu erstellen)
- **output/**: bestaetigtes Endergebnis (geht in `agent_*`,
  bleibt persistent)

Naming: `work_<slug>__in__sources`, `work_<slug>__wk__joined`,
`agent_<slug>__out__report`.

Vorteile: klare Lebenszyklus-Erwartung pro Tabelle.

Nachteile: noch laengere Namen, Mehraufwand bei jeder Tabelle.

#### C) **Auto-Discovery vor Create**

Bevor Disco eine neue work_*-Tabelle erzeugt, ruft er ein neues
Tool `find_similar_tables(purpose)` auf, das in der Lineage-Tabelle
(siehe Backlog "Data-Lineage") nach Tabellen mit aehnlichem Purpose
sucht. Trefferliste mit kurzem Match-Score wird Disco vorgelegt:

```
- work_canonical_report (purpose: "Liste aller kanonischen
  Dateien fuer SOLL/IST", 1517 rows, 2 days old)
- work_canonical_sources (purpose: "Kanonische Sources mit
  Hash-Map", 1708 rows, 1 day old)
```

Disco entscheidet dann: wiederverwenden vs. neu erstellen.

Vorteile: senkt Variant-Sprawl massiv. Setzt Lineage-Backlog
voraus.

Nachteile: nur so gut wie die `purpose`-Beschreibungen.

#### D) **Cleanup-Skill / -Tool: "raeum auf"**

Neuer Skill `workspace-cleanup`:
1. Listet alle work_*-Tabellen mit Lineage (last_used_at,
   row_count, purpose).
2. Schlaegt vor, was weg kann (Stale-Detection: > N Tage nicht
   mehr referenziert).
3. User bestaetigt pro Cluster (oder global "alle stale weg").

Vorteile: explizit, transparent.

Nachteile: User muss daran denken zu starten.

#### E) **Auto-Stale-Detection + Markierung**

Tabelle die seit 7+ Tagen nicht mehr in Lineage als Source referenziert
wurde UND nicht selbst Sources hat, die sich geaendert haben → automatisch
als `stale=1` in der Lineage markiert. UI zeigt sie ausgegraut. Nach 14
Tagen `stale=1` → Auto-Drop (mit Audit-Trail).

Vorteile: passiv, keine User-Interaktion noetig.

Nachteile: Risiko von Daten-Loss wenn Lineage unvollstaendig.

#### F) **TTL beim Create (opt-in)**

Disco-Tool `sqlite_write` bekommt optionalen Parameter
`expires_in_days=7`. Nach Ablauf wird die Tabelle automatisch
gedroppt. Gut fuer offensichtlich-temporaere Tabellen
(Test-Auswertungen, Daten-Exploration).

Vorteile: simple, opt-in, kein Mental-Load fuer Nicht-temp-Faelle.

Nachteile: User/Disco muss daran denken den Parameter zu setzen.

#### G) **UI-Hilfen** (siehe Sidebar-Backlog)

- Filter-Feld ueber der Tabellen-Liste
- Sortierung nach last_used_at
- Sub-Gruppierung an `__`-Separator (passt mit A zusammen)
- Lineage-Panel beim Anklicken einer Tabelle

#### H) **Output-Zone strikt trennen**

Konvention: bestaetigte Reports/Endergebnisse landen in `agent_*`
oder in `exports/` als File. work_* darf jederzeit weg, der User
und Disco verlassen sich darauf nicht. Disco-System-Prompt-Regel:
"work_* ist Wegwerf-Zone. Persistente Outputs gehen nach agent_*
oder exports/".

Vorteile: klare semantische Trennung, einfacher Cleanup.

Nachteile: Disziplin-Frage; muss in Skills/Prompts verankert sein.

### Querverweise zu existierenden Backlog-Eintraegen

- **Data-Lineage** ist die **Voraussetzung** fuer C, D, E (alle
  brauchen ein purpose-Feld und last_used_at).
- **Sidebar-Navigation** profitiert von A (Slug-Sub-Groups) und
  G (Filter-Feld).
- **File-Internal-Metadata** ist Quell-Provenance, hier ist's
  Ableitungs-Provenance — beides zusammen = vollstaendiges
  Datenbild.
- **Pipeline-UX** (pipeline_state) ist die Quell-Datei-Sicht;
  hier ist die Werkstatt-Daten-Sicht.

### Mein Strawman-Vorschlag fuer das Gespraech

Stufenplan, Aufwand niedrig zu hoch:

1. **Quick win — Output-Zone-Konvention (H) klarstellen**
   im System-Prompt: 1h Aufwand. Sofort wirksam fuer neue
   Tabellen.
2. **Lineage-Tabelle einfuehren** (separater BL-Eintrag,
   Voraussetzung fuer alles weitere): 3-5h.
3. **Workspace-Slug-Konzept (A)** als Ordnungsprinzip etablieren:
   in Skills/Prompts verankert, kein Code-Change noetig. 2-3h.
4. **Cleanup-Skill (D)** auf Lineage-Basis: 4-6h.
5. **Auto-Stale (E) + UI-Hilfen (G)** in einem Schwung: 1 Tag.

B (Stages), C (Auto-Discovery), F (TTL) sind eher Optional-
Features fuer eine zweite Iteration, wenn 1-5 nicht ausreichen.

### Offene Fragen fuer das Gespraech

- Wie klar wollen wir das semantische Modell machen? Hart
  durchgesetzt (Schema-Constraint) vs. Konvention im Skill?
- Wie viele Workspace-Slugs koexistieren typisch — einer
  pro Projekt-Aufgabe? Oder ein "default"-Slug + Sonder-Slugs?
- Was passiert bei Mehrfach-Konsumenten einer Tabelle (Soll
  ein gemeinsamer Output mehrere Slugs haben?).
- Soll der User Slugs explizit ankuendigen *("wir wechseln
  jetzt auf Aufgabe X")* oder soll Disco sie selbst aus dem
  Gespraech ableiten?
- Wo zeichnen wir die Linie zwischen `work_*` (Wegwerf) und
  `agent_*` (persistent)? Heute fliesst manches `work_*`
  faktisch persistent ein.

User-Quote (2026-04-27): *"Ich brauche eine Loesung wie man die
Datenverarbeitung auf Ebene 3 organisiert. Nach einigen Arbeits-
und Analyseschritten wird die Datenhaltung chaotisch und Disco
verzettelt sich mit den Daten, berechtigterweise."*
