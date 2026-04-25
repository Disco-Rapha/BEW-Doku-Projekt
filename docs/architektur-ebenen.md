# Disco — Architekturkonzept

**Stand:** 2026-04-25, gilt für Stufe 1 (DB-Split + 4-Ebenen-Datenkonzept
sind im Code umgesetzt).

**Zielgruppe:** Mitentwicklerinnen und Mitentwickler von Disco — Nutzer,
Claude, künftige Beiträger. Wer am System arbeitet, muss wissen, in
welcher Ebene etwas gehört, bevor er Tabellen anlegt, Tools baut oder
Workflows formuliert.

---

## Übersicht: zwei orthogonale Konzepte

Disco zerfällt in **zwei voneinander unabhängige Konzeptwelten**:

1. **Datenkonzept** (4 Ebenen) — was wir an Daten verwalten und wie sie
   aufeinander aufbauen. Reine Datensicht, agnostisch zu „wer arbeitet
   damit".
2. **Operating System** — die Maschinerie, mit der Disco auf den
   Datenebenen arbeitet: der Agent selbst, sein Werkzeugkasten, seine
   Playbooks, sein Gedächtnis.

```
┌──────────────────────────────────────────────────────────────────┐
│                  OPERATING SYSTEM (Disco)                         │
│                                                                  │
│   Foundry-Agent  ←  System-Prompt  ←  Tools  ←  Skills           │
│   Memory (README/NOTES/DISCO)   Flow-Library   Web-UI / CLI      │
│   Lifecycle-State (system.db + workspace.db OS-Tabellen)         │
└────────────────────────────┬─────────────────────────────────────┘
                             │ liest, schreibt, koordiniert
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                  DATENKONZEPT (4 Ebenen)                          │
│                                                                  │
│   Ebene 3  Knowledge        ← Reasoning-Ergebnisse + Reports      │
│              ↑                                                    │
│   Ebene 2  Content          ← Inhalt + Suchindex                  │
│              ↑                                                    │
│   Ebene 1  Provenance       ← Herkunfts-Register                  │
│              ↑                                                    │
│   Ebene 0  Source-Connector ← Konnektoren zu Quellsystemen        │
└──────────────────────────────────────────────────────────────────┘
```

Die Trennung erlaubt, das OS unabhängig zu evolvieren (neue Skills, neue
Tools, neuer Agent-Version, neues UI) ohne die Datenebenen anzufassen —
und umgekehrt: Datenebenen migrieren (Schema-Erweiterung, neuer
Connector-Provider) ohne den Agent neu zu bauen.

---

# Teil A — Datenkonzept (4 Ebenen)

## Warum vier Ebenen?

Drei Probleme lösen wir mit der Trennung:

1. **Herkunft sauber nachhalten.** Jedes Stück Wissen muss auf eine
   konkrete Datei, Seite und Stelle zurückführbar sein — über
   Quellwechsel, Revisionen und Format-Konversionen hinweg.
2. **Schreibzugriff entkoppeln.** Disco soll im Chat-Turn frei
   Tabellen anlegen und auswerten dürfen, ohne Gefahr zu laufen, die
   Registry oder den extrahierten Inhalt zu beschädigen.
3. **Provider-Flexibilität.** Das Projekt lebt heute auf dem lokalen
   Dateisystem, morgen kommt SharePoint, übermorgen SAP-DMS. Die
   Provenance muss diese Quellen abstrahieren, nicht davon abhängen.

## Die vier Ebenen im Überblick

| Ebene | Name | Wo liegt das | Wer schreibt | Wer liest aus dem Chat |
|---|---|---|---|---|
| **0** | **Source-Connector** | Connector-Code + Sync-State (heute trivial: User legt Datei in `sources/`/`context/` ab) | Connector-Code (heute: User selbst) | indirekt — Ebene 1 spiegelt das Resultat |
| **1** | **Provenance** | `datastore.db` (`agent_sources`, `agent_source_metadata`, `agent_source_relations`, `agent_source_scans`) | nur Registry-Tools (`sources_*`) | lesend über `ds.*`-Präfix |
| **2** | **Content** | `datastore.db` (`agent_pdf_markdown`, `agent_pdf_page_offsets`, `agent_search_*`, später Chunks + Embeddings) | nur Pipelines/Flows (`pdf_to_markdown`, `build_search_index`) | lesend über `pdf_markdown_read`, `search_index`, `ds.*` |
| **3** | **Knowledge / Workspace** | `workspace.db` (`work_*` / `agent_*` / `context_*`) + materialisierte Snapshots in `exports/` | Agent direkt + Flows | r/w |

**Kurzformel:** *Ebene 0 ist der Lieferweg. Ebene 1 weiß, woher alles
kommt. Ebene 2 weiß, was drinsteht. Ebene 3 ist das Notizbuch und der
Output-Schreibtisch.*

Datenfluss ist **streng aufwärts**. Eine höhere Ebene baut auf der
darunter auf, schreibt aber nie zurück. Re-Builds einer höheren Ebene
sind dadurch gefahrlos: Ebene 2 oder 3 kann jederzeit weggeworfen und
neu gerechnet werden, Ebene 1 bleibt unangetastet.

---

## Ebene 0 — Source-Connector

**Frage, die Ebene 0 beantwortet:** „Auf welchem Weg gelangen Dateien aus
einem Quellsystem in dieses Projekt — und welche Original-Referenzen
müssen wir uns merken, damit Drilldown ins Quellsystem möglich bleibt?"

### Was hier konzeptuell lebt

- **Connector-Code** — Module, die genau eine Quelle abfragen und
  Dateien materialisieren. Plus Sync-State: was war beim letzten Sync
  da, was ist neu, was wurde drüben gelöscht.
- **Connector-Konfiguration** — welcher SharePoint, welche Site,
  welcher Pfad, welche Pull-Frequenz. Pro Projekt.
- **Original-System-Referenzen** — die Identifier, mit denen die
  Quelle ihre Dokumente kennt (SharePoint-Item-ID, SAP-DMS-DOKUM-ID,
  Mail-Message-ID, …).
- **Authentifizierung** — Service-Account, OAuth-Token, je nach
  Provider.

### Connector-Typen (heute und Roadmap)

| Provider | Status | Was er liefert |
|---|---|---|
| `filesystem-drop` | live | User legt Datei manuell unter `sources/` oder `context/` ab |
| `zip-import` | Roadmap | Zipfile auspacken und in den Drop-Bereich einsortieren |
| `sharepoint` | Roadmap (Phase 2) | Microsoft-Graph-basierter Sync einer SP-Site |
| `sap-dms` | später | SAP-Dokumenten-API |
| `email-attachment`, `teams`, … | später | jeweils eigener Provider |

Heute existiert nur ein einziger, **passiver** Provider — der User legt
Dateien ab, fertig. Konzeptuell ist Ebene 0 trotzdem da, weil sich daraus
die Anforderungen für die nächste Generation ableiten.

### Ein Connector liefert immer dasselbe

Egal wie das Quellsystem heißt, der Output an Ebene 1 ist standardisiert:

1. **Eine Datei** im lokalen Projekt-Dateibaum (heute: physisch unter
   `sources/<…>` oder `context/<…>`).
2. **Konnektor-Metadaten** als Liefer-Bündel: `provider` (z. B.
   `sharepoint`), `origin_uid` (stabil innerhalb der Quelle),
   `origin_path`, `synced_at`, optional weitere Provider-spezifische
   Attribute.

Die stabile Identität einer Datei in Ebene 1 bleibt auch dann gleich,
wenn sich der lokale Pfad ändert — sie hängt an `provider` +
`origin_uid`, nicht am Filesystem-Pfad.

### Anforderungen, die mit Phase 2 hart werden

Heute kann Ebene 0 ignoriert werden, weil der User sie selbst spielt.
Sobald automatische Konnektoren dazukommen, muss die Schicht:

- **idempotent** sein — Mehrfach-Sync derselben Datei darf keine
  Duplikate erzeugen,
- **konfliktrobust** sein — wenn zwei Connectoren dieselbe Datei
  liefern, sauber deduplizieren oder lineage erhalten,
- **Authentifizierung kapseln** — Tokens, Service-Accounts, Rotation,
- **gelöschte Dokumente erkennen** — nicht jede Sync-Lücke ist eine
  Löschung; das muss bewusst entschieden werden.

---

## Ebene 1 — Provenance (Herkunfts-Register)

**Frage, die Ebene 1 beantwortet:** „Welche Dateien haben wir, woher
stammen sie, welche Version ist das, gibt es Duplikate oder Vorgänger?"

### Was hier gespeichert wird

- **Pro Datei genau ein Eintrag** in `agent_sources`: stabile ID,
  lokaler Pfad, Hash, Größe, Rolle (`source` / `context`),
  Registrier-Zeitstempel, Status (`active` / `superseded` / `removed`).
  Künftig zusätzlich: `provider` + `origin_uid` (heute implizit
  `filesystem-drop`).
- **Begleit-Metadaten** in `agent_source_metadata` — Excel-Sidecar,
  Provider-Attribute, freie key/value-Felder. Über die stabile ID an
  die Datei angehängt.
- **Beziehungen zwischen Dateien** in `agent_source_relations` —
  `duplicate-of`, `replaces`, `derived-from`, `format-conversion-of`.
  Werden von Registry-Tools gepflegt.
- **Scan-Historie** in `agent_source_scans` — jeder Lauf eines
  Connectors wird protokolliert (wann, welcher Provider, was hat sich
  geändert).

### Warum read-only aus Chat-Sicht

Weil jede Drift in der Registry sofort jede weitere Ebene verfälscht:
falsche Zitate, falsche SOLL/IST-Berichte, verlorene Duplikate. Disco
darf Ebene 1 lesen (über `ds.*`-Präfix) und über die kuratierten
Registry-Tools (`sources_register`, `sources_attach_metadata`,
`sources_detect_duplicates`) schreibend **auslösen** — aber niemals
freie `sqlite_write`-Eingriffe.

### Enrichment-Provider

Neben Source-Connectoren (die Binaries liefern) gibt es
**Enrichment-Provider** (die nur Metadaten liefern, z. B. eine
Excel-Sidecar-Liste mit Fachklassifikationen). Diese reichern bestehende
Einträge in `agent_source_metadata` an, ohne selbst Dateien zu bringen.
Sie sind keine eigene Ebene — sie sind eine zweite Eintrittspforte in
Ebene 1.

---

## Ebene 2 — Content (extrahierter Inhalt)

**Frage, die Ebene 2 beantwortet:** „Was steht in dieser Datei, und wo
genau auf welcher Seite?"

### Was hier gespeichert wird

- **Extrahierter Text pro Datei** — heute `agent_pdf_markdown`
  (Markdown je PDF, gefüllt vom Flow `pdf_to_markdown` mit den Engines
  docling-standard / azure-di / azure-di-hr).
- **Seiten-Index** — `agent_pdf_page_offsets` (ein Eintrag pro Seite,
  Zeichenpositionen für Drilldown).
- **Volltext-Index** (FTS5) — `agent_search_docs` +
  `agent_search_chunks_fts`, sparse part der Suche.
- **Chunks + Embeddings** (Roadmap) — kleinere Einheiten (~500–800
  Tokens) mit Backlinks auf Dokument + Seite, dazu Vektor-Embeddings
  via `sqlite-vec`. Fundament für Hybrid-Suche und Zitate.

### Warum Chunks und Embeddings auf Ebene 2 (nicht Ebene 3)

Weil sie Ableitungen vom Inhalt sind, nicht vom Reasoning. Wenn ein
Dokument reextrahiert wird (bessere Engine, neue Version), müssen
Chunks und Embeddings mitziehen — das ist eine Pipeline-Eigenschaft,
nicht Bestandteil dessen, was der Agent in seinen Projekt-Tabellen
festhält. Sobald Zitate auf Chunk-Ebene funktionieren, ist der Backlink
„Chunk → Dokument → Seite → Quelle" das Rückgrat jedes belastbaren
Reports.

### Pipelines bespielen Ebene 2

Ebene 2 wird ausschließlich über Flows und dedizierte Tools geschrieben:

- `pdf_routing_decision` + `pdf_to_markdown` — extrahiert PDFs nach
  Markdown.
- `build_search_index` — baut FTS5 auf.
- (später) Chunk-Pipeline, Embed-Pipeline.

Aus dem Chat-Turn ist Ebene 2 lesend erreichbar (über
`pdf_markdown_read`, `search_index`, künftig Embedding-Tools), aber
**nicht** über freies `sqlite_write`.

---

## Ebene 3 — Knowledge / Workspace

**Frage, die Ebene 3 beantwortet:** „Was hat Disco aus dem Material
gemacht — welche Klassifikationen, SOLL/IST-Ergebnisse, Reports?"

### Was hier gespeichert wird

- **Reasoning-Tabellen** — projektspezifische Auswertungen,
  Klassifikationen, Abgleiche, Excel-Basistabellen. Liegen in
  `workspace.db`, drei Namespaces:
  - `work_*` — temporäre Arbeit. Am Session-Ende droppen.
  - `agent_*` — dauerhafte Reasoning-Ergebnisse (z. B.
    `agent_dcc_classification`, `agent_ibl_positions`).
  - `context_*` — aus `context/`-Dateien abgeleitete Lookup-Tabellen
    (DCC-Katalog, KKS-Hierarchie, Normenmatrizen).
- **Snapshot-Artefakte** im Filesystem — `exports/<…>` enthält
  materialisierte Auswertungen (Excel-Reports, HTML-Reports,
  CSV-Auszüge). Jeder HTML-Report unter `exports/reports/<slug>/` hat
  ein begleitendes `build_<slug>.py`-Skript, das ihn reproduziert.
  Snapshots sind die **Ausleitung** des Reasoning-Stands für Menschen,
  nicht selbst Reasoning-State.
- Tabellen ohne Präfix sind in `workspace.db` gesperrt.

### Typische Workflows

- Klassifikations-Flow liest aus `ds.agent_pdf_markdown`, schreibt
  Ergebnisse in `agent_dcc_classification` (workspace.db).
- Reports joinen `agent_dcc_classification` (workspace.db) gegen
  `ds.agent_sources` (datastore.db) gegen `context_vgb_matrix`
  (workspace.db).
- HTML-/Excel-Export baut auf Ergebnis-Tabellen aus workspace.db und
  zitiert zurück auf `ds.agent_sources` + `ds.agent_pdf_markdown` für
  Quellennachweise.

---

## Quer-Layer: `context/`

`context/` ist **kein eigener Connector und keine eigene Ebene**, sondern
ein **Quer-Layer**, der jede Datenebene berührt:

- **Auf Ebene 0** kommt eine Norm/Katalog-Datei genauso über einen
  Connector ins Projekt wie eine `source/`-Datei.
- **Auf Ebene 1** wird sie genauso registriert wie eine source-Datei,
  aber mit Rolle `context`.
- **Auf Ebene 2** wird sie genauso extrahiert und indiziert.
- **Auf Ebene 3** entstehen aus ihr `context_*`-Lookup-Tabellen, gegen
  die das Reasoning läuft.

Konzeptuell ist `context/` die **Brille, durch die Disco die `sources/`
liest** — Normen, Kataloge, Hierarchien, Standardvorgaben. Der
Mechanismus ist derselbe wie bei sources, der Zweck ist ein anderer:
sources sind das Material, context ist der Maßstab.

Die starre Trennung über Wurzelordner (`sources/` vs. `context/`) bleibt
wichtig: sie macht Reasoning unzweideutig (was wird klassifiziert vs.
was klassifiziert) und Reports zitierbar.

---

## Zugriffsmatrix

Kompakte Übersicht, wer wie an welche Datenebene kommt:

| Ebene | Schreiben aus Chat | Lesen aus Chat | Befüllt durch |
|---|---|---|---|
| 0 — Source-Connector | nein (Connector-Code, heute: User-Hand) | indirekt über Ebene 1 | Connector-Provider |
| 1 — Provenance | nein (nur über Registry-Tools) | `sqlite_query` über `ds.*` | Source-/Enrichment-Provider, Registry-Tools |
| 2 — Content | nein (nur über Pipelines) | `pdf_markdown_read`, `search_index`, `ds.*` | Flows (`pdf_to_markdown`, `build_search_index`) |
| 3 — Knowledge / Workspace | `sqlite_write` im Namespace + `fs_write` für `exports/` | `sqlite_query`, `fs_read` | Agent + Flows |

---

## Regeln, die Disco verinnerlicht

Diese Regeln fließen 1:1 in den System-Prompt — hier als kompakter
Referenzblock:

1. **Architektur kennen.** Vier Datenebenen. Ebene 1 + 2 in
   `datastore.db` (read-only aus dem Chat, erreichbar über `ds.*`),
   Ebene 3 in `workspace.db` (frei beschreibbar mit `sqlite_write` im
   `work_*`/`agent_*`/`context_*`-Namespace). Ebene 0 ist heute
   passiv (User-Drop), bleibt aber konzeptuell präsent.
2. **Binaries nicht in den Chat-Kontext lesen.** Inhalt von
   registrierten Dateien kommt aus Ebene 2 (`pdf_markdown_read`,
   `search_index`), nicht aus `fs_read` auf `.pdf`. `fs_read` ist für
   Memory-, Manifest-, Script- und Textdateien.
3. **Provenance nicht mit SQL verbiegen.** Einträge in
   `ds.agent_sources`, `ds.agent_source_metadata`,
   `ds.agent_source_relations` ändert der Agent **nie** direkt — nur
   über `sources_register`, `sources_attach_metadata`,
   `sources_detect_duplicates`.
4. **Rolle folgt dem Ordner.** Datei in `sources/` = Rolle `source`,
   in `context/` = Rolle `context`. Keine Overrides, keine
   Mischordner. Wenn der Nutzer eine Datei in beiden Rollen braucht,
   bittet Disco ihn, sie zu duplizieren — nicht, sie umzudeklarieren.
5. **Zitierbar arbeiten.** Jede Aussage, die aus einem Projekt-
   Dokument stammt, bekommt einen Backlink auf die Quelle (heute:
   Dateipfad + Seitenzahl; künftig: Chunk-ID). Wenn die Information
   nicht belegbar ist, sagt Disco das offen — er erfindet nichts.

---

# Teil B — Operating System (Disco)

Alles, was nicht Daten ist, gehört hierher. Der Disco-Agent ist eine
**eigenständige Maschinerie**, die mit den Datenebenen arbeitet, aber
selbst nicht Teil davon ist.

## Komponenten

| Komponente | Wo | Zweck |
|---|---|---|
| **Foundry-Agent** | Foundry-Portal (`disco-prod-agent`, `disco-dev-agent`) | Modell-Deployment + System-Prompt + Tool-Schema, versioniert |
| **System-Prompt** | `src/disco/agent/system_prompt.md` | Persönlichkeit, Regeln, Trigger-Tabelle, Tool-Doku |
| **Tools** | `src/disco/agent/functions/*.py` | Atomare Operationen (fs_*, sqlite_*, sources_*, pdf_*, run_python, search_index, …) |
| **Skills** | `skills/*.md` | Kuratierte Playbooks (lazy-loaded) |
| **Flow-Library** | `src/disco/flows/library/<name>/runner.py` | Code für Massenverarbeitung |
| **Memory** | `<projekt>/README.md` + `NOTES.md` + `DISCO.md` | Discos Langzeit-Gedächtnis pro Projekt |
| **Internes** | `<projekt>/.disco/` | Sessions, Pläne, Context-Extracts/Summaries, lokale Skills, Skripte |
| **Lifecycle-State** | `workspace.db` (`agent_flow_runs`, `agent_flow_run_items`, `agent_flow_notifications`, `agent_script_runs`) | Audit + Run-Tracking |
| **Web-UI / CLI** | `src/disco/api/`, `src/disco/cli.py` | Wie der User mit Disco redet |
| **System-DB** | `~/Disco/system.db` | Projekt-Verzeichnis, Threads, Messages — projektübergreifend |

## Memory — die drei Dateien

Zwischen Sessions vergisst Disco alles, was nicht in diesen drei Dateien
steht:

| Datei | Wer pflegt | Was steht drin |
|---|---|---|
| **README.md** | Nutzer | Projekt-Briefing: Ziel, Auftraggeber, Erwartungen, KPIs |
| **NOTES.md** | Disco | Chronologisches Logbuch (append-only) |
| **DISCO.md** | Disco | Destilliertes Arbeitsgedächtnis: Konventionen, Tabellen-Inventar, Glossar, Entscheidungen |

DISCO.md ist das wichtigste — das ist der Snapshot, der Disco nach einer
Kompression sofort wieder arbeitsfähig macht.

## Lifecycle-State liegt physisch in `workspace.db`

Eine pragmatische Verkürzung: die OS-Lifecycle-Tabellen
(`agent_flow_runs`, `agent_script_runs`, `agent_flow_notifications`)
liegen in derselben DB wie die Reasoning-Daten der Ebene 3.
**Konzeptuell** sind sie OS-State, nicht Knowledge. Die Vermischung ist
heute akzeptabel, weil eindeutige Tabellennamen die Trennung
ausreichend klar machen.

Falls die Vermischung später stört: dritte DB `os.db` einziehen,
analog zum bisherigen Split datastore/workspace.

## System-Prompt + Tools + Skills + Flows — die Vier-Schicht-Maschine

Innerhalb des OS gibt es eine eigene Schichtung der Verantwortung:

| Schicht | Was | Wann |
|---|---|---|
| **System-Prompt** | Persönlichkeit, Regeln, Trigger-Tabelle, Tool-Doku | immer im Kontext |
| **Tools** | Atomare Operationen (eine Sache, gut testbar) | jederzeit aufrufbar |
| **Skills** | Kuratierte Playbooks (*"so machst Du X"*) | per Trigger geladen, dann befolgt |
| **Flows** | Massenverarbeitung als Subprocess (>10 Items / >2 Min) | resumable, pausierbar, mit Lifecycle-Tracking |

Neue Funktionalität bekommt fast immer eine eindeutige Heimat:
- Atomare Operation → neues Tool in `agent/functions/`
- Wiederkehrendes Multi-Step-Muster → neuer Skill in `skills/`
- Massenverarbeitung → neuer Flow in `flows/library/`
- Persönlichkeitsänderung / globale Regel → System-Prompt-Edit

## Versionierung getrennt vom Datenkonzept

OS-State und Datenebenen migrieren über getrennte Schemata:

- **OS / projektübergreifend:** `migrations/*.sql` → `system.db`
- **OS / pro Projekt (Lifecycle):** `migrations/project/workspace/*.sql`
- **Datenkonzept Ebene 1+2:** `migrations/project/datastore/*.sql`
- **Datenkonzept Ebene 3:** Tabellen entstehen ad-hoc per
  `sqlite_write`, kein Migrations-Schema (das ist Reasoning-State, nicht
  Strukturwissen).

---

# Teil C — Stand und Roadmap

## Stand 2026-04-25 (Stufe 1 erreicht)

- DB-Split `datastore.db` ↔ `workspace.db` umgesetzt, ATTACH-Setup im
  Agent-Loop (`ds.*`-Präfix für read-only-Zugriff auf Ebene 1+2).
- Provenance- (Ebene 1) und Content- (Ebene 2) Tabellen in
  `datastore.db`, Reasoning-Tabellen + Lifecycle-State in
  `workspace.db`.
- FTS5-Suchindex (Phase 0 von Ebene 2) live: `build_search_index` +
  `search_index`.
- PDF-Pipeline (`pdf_routing_decision` + `pdf_to_markdown`) befüllt
  Ebene 2 mit drei Engines (docling-standard / azure-di / azure-di-hr).
- Connector-Schicht (Ebene 0) **konzeptuell** dokumentiert, aber
  technisch trivial: einziger Provider ist `filesystem-drop`.

## Kommende Stufen (Reihenfolge nicht verbindlich)

- **Stufe 2 — Connector-Abstraktion.** `agent_sources.provider` +
  `origin_uid` als explizite Felder, `filesystem-drop` und
  `zip-import` als erste Provider-Implementierungen, Sync-State in
  einer eigenen Tabelle.
- **Stufe 3 — Hybrid-Suche.** Chunks + Embeddings via `sqlite-vec`
  parallel zu FTS5, Hybrid-Ranking. Fundament für Zitate auf
  Chunk-Ebene.
- **Stufe 4 — Revisions-Reasoning.** `replaces`-Erkennung aus
  Filename-/Inhalts-Pattern als Standard-Skill, statt manuell.
- **Stufe 5 — SharePoint-Connector.** Erster nicht-trivialer
  Ebene-0-Provider, MSAL-OAuth, Microsoft-Graph-Sync.

Jede Stufe ist ein eigener PR und kann einzeln gemerged werden.

---

# Teil D — Was NICHT Teil dieses Konzepts ist

- **Postgres.** Bleibt SQLite, mehrere Dateien pro Projekt.
- **Zentrale Registry über mehrere Projekte.** Jedes Projekt behält
  seine eigene `datastore.db` und `workspace.db`. Mandantentrennung
  bleibt.
- **Automatische Rollen-Ableitung aus Dateiinhalten.** Rolle kommt
  vom Wurzelordner, Punkt.
- **Global shared `context/`.** Auch hier bleibt alles projekt-lokal
  — eine Norm, die in zwei Projekten gebraucht wird, wird zweimal
  importiert.
- **OS-State und Datenkonzept in derselben Migration.** OS-Migrationen
  (`migrations/`, `migrations/project/workspace/`) und Daten-Migrationen
  (`migrations/project/datastore/`) bleiben getrennt.
