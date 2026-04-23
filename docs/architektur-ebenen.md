# Disco — Architektur-Ebenen

**Status:** Konzept (Stufe 0). Gilt als Zielbild für die Umbau-Reihe
in der Architektur-Layers-Initiative. Einzelne Ebenen werden stufen-
weise umgesetzt; dieses Dokument beschreibt das Ziel, nicht den
heutigen Stand im Code.

**Zielgruppe:** Mitentwicklerinnen und Mitentwickler von Disco —
Nutzer, Claude, künftige Beiträger. Wer am System arbeitet, muss
wissen, in welcher Ebene etwas gehört, bevor er Tabellen anlegt,
Tools baut oder Workflows formuliert.

---

## Warum vier Ebenen?

Disco hatte bis hierher **eine** Datenbank pro Projekt (`data.db`)
und eine eher schwammige Trennung zwischen Registry-Kram,
extrahiertem Inhalt und Arbeits­tabellen. Das hat bis ~1.800 Dateien
funktioniert. Für ein Projekt mit **6.000 Dokumenten** über mehrere
Quellen, mit kontinuierlichem Nachschub, Revisionen, Duplikaten und
Cross-Source-Reasoning reicht das nicht mehr.

Drei Probleme lösen wir mit der Trennung:

1. **Herkunft sauber nachhalten.** Jedes Stück Wissen muss auf eine
   konkrete Datei, Seite und Stelle zurückführbar sein — über
   Quellwechsel, Revisionen und Format-Konversionen hinweg.
2. **Schreibzugriff entkoppeln.** Disco soll im Chat-Turn frei
   Tabellen anlegen und auswerten dürfen, ohne Gefahr zu laufen, die
   Registry oder den extrahierten Inhalt zu beschädigen.
3. **Provider-Flexibilität.** Das Projekt lebt heute auf dem
   lokalen Dateisystem, morgen kommt SharePoint, übermorgen SAP-DMS.
   Die Registry muss diese Quellen abstrahieren, nicht davon abhängen.

---

## Die vier Ebenen im Überblick

| Ebene | Name | Wo liegt das | Wer darf schreiben | Wer darf lesen |
|---|---|---|---|---|
| **0** | **Agent-Workspace** | Projektordner (Dateien + Memory) | Der Agent (`fs_*`, `memory_*`) und der Nutzer | Agent und Nutzer |
| **1** | **Provenance** (Herkunfts-Register) | `datastore.db` | Nur Registry-Tools (`sources_*`, Source-Provider) | Agent lesend über `datastore_*` bzw. `ds.*`-Präfix |
| **2** | **Content** (extrahierter Inhalt) | `datastore.db` | Nur Pipelines (PDF→Markdown, Chunking, Embeddings) | Agent lesend |
| **3** | **Knowledge / Workspace** (Reasoning-Ergebnisse) | `workspace.db` | Der Agent (`sqlite_write`) und Flows | Agent lesend + schreibend |

**Kurzformel:** *Ebene 0 ist der Schreibtisch. Ebene 1 weiß, woher
alles kommt. Ebene 2 weiß, was drinsteht. Ebene 3 ist das Notizbuch
des Agents.*

Die physische Aufteilung:

- **`datastore.db`** enthält Ebene 1 + Ebene 2. Aus Sicht des
  Chat-Turns **read-only**. Wird ausschließlich von Registry-Tools
  und Pipelines befüllt.
- **`workspace.db`** enthält Ebene 3. Der Agent darf dort mit
  `sqlite_write` frei arbeiten — Tabellen anlegen, füllen, droppen.

Beide DBs sitzen nebeneinander im Projektordner. Wenn der Agent in
einem Query auf beide zugreifen muss (z. B. Provenance joinen gegen
eigene Klassifikation), wird `datastore.db` als `ds` über
`ATTACH DATABASE` in die Workspace-Session eingehängt; Tabellen aus
der Registry erreicht er dann über `ds.agent_sources`, Tabellen in
der eigenen DB ohne Präfix.

---

## Ebene 0 — Agent-Workspace

Die Ebene, die der Nutzer im Dateibrowser sieht. Der Projektordner
liegt unter `~/Disco/projects/<slug>/`.

### Ziel-Layout

```
<projekt>/
├── README.md         ← Nutzer pflegt: Projektziel, Kontext, Erwartungen
├── NOTES.md          ← Disco pflegt: chronologisches Logbuch
├── DISCO.md          ← Disco pflegt: destilliertes Arbeitsgedächtnis
├── sources/          ← role = source (Arbeitsdokumente)
│   └── _meta/        ← Begleit-Excel, nicht gescannt
├── context/          ← role = context (Nachschlagewerke)
│   └── _manifest.md  ← Disco-gepflegte Übersicht
├── exports/          ← Endprodukte für den Nutzer (nie überschreiben)
├── datastore.db      ← Ebene 1 + 2 (Provenance + Content)
├── workspace.db      ← Ebene 3 (Reasoning / Projekt-Tabellen)
└── .disco/           ← Interne Artefakte (Extrakte, Sessions, Indizes)
```

**Bewusst entfallen gegenüber dem Alt-Layout:**

- `plans/` — in der Praxis nie genutzt. Mehrstufige Vorhaben
  leben im Chat und in DISCO.md.
- `work/` — in der Praxis nie genutzt. Zwischenstände landen in
  Ebene 3 (`workspace.db`) oder unter `.disco/`.

### Rollen-Modell: binär, nicht konfigurierbar

Jede Datei im Projekt hat genau **eine** Rolle — `source` oder
`context` — und diese Rolle ergibt sich **ausschließlich** aus dem
Wurzel­ordner, in dem sie liegt:

- Alles unter `sources/` → Rolle `source`.
- Alles unter `context/` → Rolle `context`.

Es gibt **keine** Mischordner, **keine** Override-Attribute,
**keine** Rollen-Mehrfachzuordnung. Wenn eine Norm gleichzeitig als
Nachschlagewerk *und* als klassifizierungs­pflichtige Quelle
gebraucht wird, **dupliziert der Nutzer die Datei** bewusst — einmal
in `sources/`, einmal in `context/`. Beide Kopien werden getrennt
registriert, getrennt extrahiert, getrennt zitierbar.

Warum so starr? Weil die Alternative — dieselbe Datei mit zwei
Rollen, „overrides" im Metadata-Blob, Mischordner mit Marker-Dateien —
die Pipeline, die Suche, die Zitate und die Reports um eine
Dimension komplizierter macht, ohne einen echten Nutzen zu liefern.
Dateien zu duplizieren ist billig; Regel-Drift ist teuer.

### Was lebt sonst in Ebene 0

- **Memory** (README/NOTES/DISCO) — das Projekt-Gedächtnis. Wird
  ausschließlich über `memory_*`-Tools angefasst.
- **`.disco/`** — alles, was Disco *für sich* braucht, aber nicht
  Teil der inhaltlichen Arbeit ist: Session-Logs, DI-Extrakte
  (Roh-Antworten von Azure Document Intelligence), Kontext-
  Zusammenfassungen, Suchindex-Artefakte. Der Nutzer darf dort
  hineinschauen, soll aber nichts editieren.

---

## Ebene 1 — Provenance (Herkunfts-Register)

**Frage, die Ebene 1 beantwortet:** „Woher stammt diese Datei, wie
heißt sie in ihrer Quelle, welche Version ist das, gibt es Duplikate
oder Vorgänger?"

### Was hier gespeichert wird

- Jede registrierte Datei bekommt genau einen Eintrag:
  stabile ID, Provider-Herkunft (`origin_provider`, `origin_uid`),
  lokaler Pfad, Größe, SHA-256, Rolle (`source` / `context`),
  Registrier-Zeitstempel, Status (`active` / `superseded` / `removed`).
- **Begleit-Metadaten** (Excel-Sidecar, Provider-Attribute): separate
  Tabelle, über die stabile ID an die Datei angehängt.
- **Beziehungen zwischen Dateien** — `duplicate-of`, `replaces`,
  `derived-from`, `format-conversion-of`. Werden von Registry-Tools
  gepflegt, nicht vom Agent.
- **Scan-Historie** — jeder Lauf eines Source-Providers wird
  protokolliert (wann, welcher Provider, was hat sich geändert).

### Source-Provider — die Plug-in-Stelle

Dateien kommen nicht von selbst in Ebene 1. Ein **Source-Provider**
ist die Instanz, die Binärdateien beschafft und sie der Registry
zur Aufnahme übergibt. Jeder Provider kennt genau eine Quelle:

- `filesystem` — Dateien liegen bereits lokal unter `sources/`
  oder `context/`. Heutiger Default.
- `zip-import` — Zipfile wird ausgepackt und eingesortiert.
- `sharepoint` — Microsoft-Graph-basierter Sync (Phase 2).
- `sap-dms` — SAP-Dokumenten-API (später).
- `email-attachment`, `teams`, etc. — jeweils eigener Provider.

Ein Provider liefert pro Datei: Binary, `origin_provider`,
`origin_uid` (stabil innerhalb der Quelle), Roh-Metadaten. Die
Registry schreibt den Eintrag und weist dem Binary einen lokalen
Pfad zu. Die stabile ID bleibt auch dann dieselbe, wenn die Datei
später woanders hinwandert oder ein neuer Provider denselben
Gegenstand liefert (Identität über `origin_provider` + `origin_uid`,
Dublettenerkennung zusätzlich über SHA-256).

Neben Source-Providern (die Binaries liefern) gibt es
**Enrichment-Provider** (die nur Metadaten liefern, z. B. eine
Excel-Sidecar-Liste mit Fach­klassifikationen). Diese reichern
bestehende Einträge an, ohne selbst Dateien zu bringen.

### Warum auf Ebene 1 read-only aus Chat-Sicht?

Weil jede Drift in der Registry sofort jede weitere Ebene
verfälscht: falsche Zitate, falsche SOLL/IST-Berichte, verlorene
Duplikate. Der Agent darf Ebene 1 lesen (für Reasoning) und über
die kuratierten Registry-Tools (`sources_register`,
`sources_attach_metadata`, `sources_detect_duplicates`) schreibend
**auslösen** — aber keine freien `sqlite_write`-Eingriffe.

---

## Ebene 2 — Content (extrahierter Inhalt)

**Frage, die Ebene 2 beantwortet:** „Was steht in dieser Datei, und
wo genau auf welcher Seite?"

### Was hier gespeichert wird

- **Extrahierter Text pro Datei** — heute: `agent_pdf_markdown`
  (Markdown je PDF, gefüllt vom Flow `pdf_to_markdown`). Perspek­tivisch
  auch Markdown aus Excel-/Word-Extraktoren.
- **Chunks** (später) — kleinere Einheiten (~500–800 Tokens) mit
  Metadaten: Dokument-Backlink, Seitenzahl, nächstliegende
  Überschrift. Fundament für Zitate.
- **Embeddings** (später) — Vektoren pro Chunk, Backlink auf Chunk +
  Dokument. Fundament für Hybrid-Suche.
- **Volltext-Index** (FTS5) — sparse part der Suche. Schon teilweise
  vorhanden (`agent_search_*`), wandert vollständig in Ebene 2.

### Warum Chunks und Embeddings auf Ebene 2 (nicht Ebene 3)?

Weil sie Ableitungen vom Inhalt sind, nicht vom Reasoning. Wenn ein
Dokument reextrahiert wird (bessere Engine, neue Version), müssen
Chunks und Embeddings mitziehen — das ist eine Pipeline-Eigenschaft,
nicht Bestandteil dessen, was der Agent in seinen Projekt-Tabellen
festhält. Und: sobald Zitate auf Chunk-Ebene funktionieren, ist der
Backlink „Chunk → Dokument → Seite → Quelle" das Rückgrat jedes
belastbaren Reports.

### Pipelines bespielen Ebene 2

Ebene 2 wird ausschließlich über Flows und dedizierte Tools
geschrieben:

- `pdf_routing_decision` + `pdf_to_markdown` — extrahiert PDFs
  nach Markdown.
- `build_search_index` — baut FTS5 auf.
- (später) Chunk-Pipeline, Embed-Pipeline.

Auch hier gilt: Aus dem Chat-Turn ist Ebene 2 lesend erreichbar
(über `pdf_markdown_read`, `search_index`, künftig Embedding-
Tools), aber **nicht** über freies `sqlite_write`.

---

## Ebene 3 — Knowledge / Workspace (Reasoning-Ergebnisse)

**Frage, die Ebene 3 beantwortet:** „Was hat Disco aus dem Material
gemacht — welche Klassifikationen, SOLL/IST-Resultate, Exports?"

### Was hier gespeichert wird

- Projekt-spezifische Reasoning-Tabellen — Klassifikationen,
  Abgleiche, Lookup-Strukturen, Excel-Basistabellen für Reports.
- Kontext-Lookup-Tabellen, die Disco aus `context/`-Dateien aufbaut
  (DCC-Katalog, KKS-Hierarchie, Normen­matrizen).
- Flow-Artefakte — `agent_flow_runs`, `agent_flow_run_items`,
  `agent_script_runs`.
- Arbeitszustände (`work_*`), die der Agent selbst setzt und wieder
  wegräumt.

### Namespace-Disziplin

Die heute etablierte Drei-Teilung bleibt, lebt aber in
`workspace.db`:

- `work_*` — temporäre Arbeit. Am Session-Ende droppen.
- `agent_*` — dauerhafte Arbeit. Klassifikations­ergebnisse,
  SOLL/IST, eigene Analysen.
- `context_*` — aus `context/`-Dateien abgeleitete Lookup-Tabellen.

Tabellen ohne Präfix sind gesperrt.

### Typische Workflows

- Klassifikations-Flow liest aus `ds.agent_pdf_markdown`, schreibt
  Ergebnisse in `agent_dcc_classification` (workspace.db).
- Reports joinen `agent_dcc_classification` (workspace.db) gegen
  `ds.agent_sources` (datastore.db) gegen `context_vgb_matrix`
  (workspace.db).
- Excel-Export baut auf Ergebnis-Tabellen aus workspace.db und
  zitiert zurück auf `ds.agent_sources` + `ds.agent_pdf_markdown`
  für Quellennachweise.

---

## Zugriffsmatrix

Kompakte Übersicht, wer wie an welche Ebene kommt:

| Ebene | Schreiben aus Chat | Lesen aus Chat | Befüllt durch |
|---|---|---|---|
| 0 — Agent-Workspace | `fs_write`, `fs_mkdir`, `memory_*` | `fs_list`, `fs_read`, `memory_read` | Agent + Nutzer |
| 1 — Provenance | nein (nur über Registry-Tools) | `datastore_query` / `ds.*` | Source-Provider, Registry-Tools |
| 2 — Content | nein (nur über Pipelines) | `pdf_markdown_read`, `search_index`, `ds.*` | Flows (`pdf_to_markdown`, FTS5-Build) |
| 3 — Knowledge/Workspace | `sqlite_write` im Namespace | `sqlite_query` | Agent + Flows |

---

## Regeln, die Disco verinnerlicht

Die folgenden Regeln fließen 1:1 in den System-Prompt — hier als
kompakter Referenz­block:

1. **Architektur kennen.** Es gibt vier Ebenen. Ebene 1 und 2 liegen
   in `datastore.db` (read-only aus dem Chat, erreichbar via
   `datastore_*`-Tools bzw. `ds.*`-Präfix), Ebene 3 lebt in
   `workspace.db` (frei beschreibbar mit `sqlite_write` im
   `work_*`/`agent_*`/`context_*`-Namespace).
2. **Binaries nicht in den Chat-Kontext lesen.** Inhalt von
   registrierten Dateien kommt aus Ebene 2 (`pdf_markdown_read`,
   `search_index`), nicht aus `fs_read` auf `.pdf`. `fs_read` ist für
   Memory-, Manifest-, Script- und Textdateien.
3. **Provenance nicht mit SQL verbiegen.** Einträge in
   `ds.agent_sources`, `ds.agent_source_metadata`,
   `ds.agent_source_relations` ändert der Agent **nie** direkt — nur
   über `sources_register`, `sources_attach_metadata`,
   `sources_detect_duplicates`.
4. **Rolle folgt dem Ordner.** Datei in `sources/` = Rolle
   `source`. Datei in `context/` = Rolle `context`. Keine
   Overrides, keine Mischordner. Wenn der Nutzer eine Datei in
   beiden Rollen braucht, bittet Disco ihn, sie zu duplizieren —
   nicht, sie „umzudeklarieren".
5. **Zitierbar arbeiten.** Jede Aussage, die aus einem Projekt-
   Dokument stammt, bekommt einen Backlink auf die Quelle (heute:
   Dateipfad + Seitenzahl; künftig: Chunk-ID). Wenn die Information
   nicht belegbar ist, sagt Disco das offen — er erfindet nichts.

---

## Migrationspfad (grob, nicht verbindlich)

Dieses Dokument ist das **Ziel**. Der Umbau läuft in Stufen:

- **Stufe 0** — Konzept + System-Prompt-Regeln (dieser PR).
- **Stufe 1** — DB-Split vorbereiten: Migrations-Aufteilung in
  `datastore.db` vs. `workspace.db`, ATTACH-Setup in der Agent-
  Session.
- **Stufe 2** — Source-Provider-Abstraktion: `filesystem` und
  `zip-import` als erste Provider, Registry gegen Provider-ID +
  UID bauen.
- **Stufe 3** — Pipelines (PDF→MD, Suchindex) auf Ebene 2 heben,
  Tool-API entsprechend anpassen.
- **Stufe 4** — Reasoning-Tabellen nach `workspace.db` ziehen,
  Flows anpassen.
- **Stufe 5** — Chunks + Embeddings + Zitate-Backlinks einziehen.

Jede Stufe hat einen eigenen PR und kann einzeln gemerged werden.

---

## Was NICHT Teil dieses Konzepts ist

- **Postgres.** Bleibt SQLite, mehrere Dateien pro Projekt.
- **Zentrale Registry.** Jedes Projekt behält seine eigene
  `datastore.db` und `workspace.db`. Mandantentrennung bleibt.
- **Automatische Rollen-Ableitung aus Dateiinhalten.** Rolle kommt
  vom Ordner, Punkt.
- **Global shared `context/`.** Auch hier bleibt alles projekt-lokal.
- **Neue Foundry-Tools in diesem PR.** Die Tool-API ändert sich erst
  mit Stufe 1 ff.
