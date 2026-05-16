# Pipeline-Reform v2: Hash-zentrierte datastore.db

**Status:** Konzept abgeschlossen 2026-05-16. Migration startet in DEV.
**Notion-BL:** wird beim BL-Item-Anlegen verlinkt.

---

## TL;DR

Die `datastore.db` wird von **pfad-zentriert** auf **hash-zentriert** umgestellt:
eine Zeile pro eindeutigem Datei-Inhalt (`sha256` UNIQUE), eine separate
Tabelle für Ablageorte. Beziehungen zwischen Dateien (duplicate-of,
replaces, derived-from) entfallen — sie ergeben sich strukturell oder
werden bewusst nicht modelliert. workspace.db referenziert via stabiler
`source_id` und pinnt `sha256` zur Audit-Sicherheit.

**Effekt:** Extraktion läuft pro Inhalt einmal (rea-denox: 68% Duplikat-Anteil →
~3× weniger Extraktions-Aufwand), Move/Rename ist trivial, Sync-Workflow
ohne Manifest möglich, workspace-Auswertungen sind stabil über Lebenszyklen.

---

## Motivation

Heutiges Modell:
- `agent_sources` enthält eine Zeile pro `(rel_path, sha256)`-Kombination
- Duplikate sind eigene Zeilen, verknüpft per `agent_source_relations.kind='duplicate-of'`
- SharePoint-Felder leben am `agent_sources`-Eintrag, nicht am Ablageort
- Move/Rename wird heute nicht explizit erkannt — eine umbenannte Datei
  wirkt wie „alt gelöscht + neu hinzugekommen"

Probleme im Alltag:
1. **Re-Extraktion** läuft im Zweifel mehrfach (Markdown wird zwar dedupliziert,
   aber die Routing-Logik ist komplex)
2. **Ordner-Rename** in SP → für Disco wirkt jede Datei plötzlich „neu"
3. **Workspace-Auswertungen** zeigen auf Pfad-Identitäten, die instabil sind
4. **Multi-User-Vision** (eine zentrale datastore, mehrere workspaces) ist
   strukturell schwer, solange Beziehungen verteilt sind

---

## Zielmodell

### Drei klare Schichten

```sql
-- Schicht 1: Inhalt-Identität (eine Zeile pro Hash)
CREATE TABLE agent_sources (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  sha256            TEXT NOT NULL UNIQUE,    -- Identitäts-Schlüssel
  size              INTEGER,
  status            TEXT NOT NULL,           -- 'active' / 'deleted'
  first_seen_at     TEXT NOT NULL,
  last_seen_at      TEXT NOT NULL,
  -- Inhalt-Extractions (Hash-gebunden):
  markdown          TEXT,
  markdown_meta     JSON,
  summary           TEXT,                    -- (zukünftig)
  vision_extraction JSON,                    -- (zukünftig)
  intrinsic_meta    JSON                     -- dateieigene Meta (PDF-Author etc.)
);

-- Schicht 2: Ablage (mehrere Zeilen pro Hash möglich)
CREATE TABLE agent_source_locations (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id         INTEGER NOT NULL REFERENCES agent_sources(id),
  rel_path          TEXT NOT NULL,           -- aktueller FS-Pfad
  logical_path      TEXT,                    -- z.B. SP-Pfad, optional
  origin            TEXT NOT NULL,           -- 'sp-libname-full' / 'incr-2026-w20' / 'manual'
  status            TEXT NOT NULL,           -- 'active' / 'deleted'
  first_seen_at     TEXT NOT NULL,
  last_seen_at      TEXT NOT NULL,
  external_meta     JSON                     -- SharePoint-Feld-Snapshot
);

-- Schicht 3: Suchindizes (Hash-gebunden)
agent_source_fts        -- FTS5 virtual table, joined via source_id
agent_source_embeddings -- (zukünftig) vector-Tabelle
```

### Designentscheidungen — explizit verankert

| Entscheidung | Begründung |
|---|---|
| `sha256` UNIQUE in agent_sources | Eine Zeile pro Inhalt, keine Spezialfall-Duplikat-Logik |
| `rel_path` NICHT UNIQUE in locations | Historie pro Pfad sichtbar (alt deleted + neu active) |
| Versionen = delete + new | Keine `supersedes`-Pointer, keine Versions-Trees |
| Keine `replaces`-Relations | Konsequenz aus „delete + new" |
| Keine `derived-from`-Relations | datastore speichert keine Datei-Beziehungen |
| Soft-Delete für sources UND locations | Workspace-Annotationen bleiben stabil |
| Wiederauferstehung möglich | `deleted` → `active`, wenn Hash+Pfad zurückkommt |
| SharePoint-Meta an location, nicht source | SP-Meta ist Ablage-spezifisch |
| Datei-eigene Meta an source | Aus dem Inhalt extrahiert |
| Markdown an source, nicht location | Hash-gebunden, einmal pro Inhalt |

### Was NICHT modelliert wird

- **Logisches Dokument** als eigene Entität — User-Entscheidung: zu viel
  Struktur für den Nutzen
- **Versions-Kette** — `supersedes` wäre eine Verbindung, wollen wir nicht
- **derived-from** (DWG→PDF Konversion) — falls relevant: workspace-Annotation
- **canonical-flags** auf Locations — eine zur Anzeige zu wählende Location
  wird ad-hoc per Disambig-Regel bestimmt (z.B. „active + geprüft-Ordner")

---

## Datei-Cases — vollständige Verhaltens-Spezifikation

| Case | Erkennung | datastore.db | workspace.db |
|---|---|---|---|
| **C1** Neue Datei (neuer Hash) | Hash unbekannt | INSERT agent_sources + agent_source_locations | unberührt |
| **C1'** Neue Location (Hash schon da) | Hash bekannt, Pfad neu | NUR agent_source_locations INSERT — keine Re-Extraktion | unberührt |
| **C2/C3** Move/Rename | Hash gleich, Pfad neu, kein neuer Eintrag mit altem Hash | UPDATE locations.rel_path | unberührt (ID-Pin stabil) |
| **C4/C10** Neue Version | Pfad bekannt, Hash neu | alte location → `deleted`, neue Zeile mit neuer source_id; alte source bleibt | bestehende Annotations bleiben an V1 (Markdown bleibt erreichbar); Disco-Hint: „V2 ist da" |
| **C5** Duplikat-Hochladung | Hash gleich, neuer Pfad | C1' (zweite Location an gleichem source) | unberührt |
| **C6** Datei gelöscht | Pfad nicht mehr im Scan | location → `deleted`; wenn letzte active location der source weg → source.status='deleted' | Annotations bleiben mit Stub „archiviert" |
| **C7** Metadaten kommen hinzu | External-Quelle liefert Felder | UPDATE locations.external_meta | unberührt |
| **C8** Metadaten geändert | gleicher key, neuer value | UPDATE locations.external_meta | unberührt |
| **C9** Metadaten gelöscht | Field-Quelle ist weg / leer | UPDATE locations.external_meta (Field weg) | unberührt |
| **C0** Keine Metadaten vorhanden | external_meta = NULL | trivial | trivial |
| **CR** Wiederauferstehung | Pfad + Hash beide bekannt, aktuell deleted | location.status → 'active'; if source.status='deleted' → 'active'; Markdown bleibt unverändert | Annotations werden wieder valid |

**Konflikt-Regel bei Wiederauferstehung:** Wenn am gleichen `rel_path` bereits
eine `active` location mit anderem Hash steht (Versions-Folge), bleibt die
alte deleted. An einem Pfad lebt nur eine aktive Datei.

---

## Workspace-Bindung

### Pin-Pattern pro Auswertungs-Zeile

```sql
-- Standard-Pattern für jede work_*-Tabelle, die auf eine Datei zeigt:
source_id              INTEGER NOT NULL,   -- Inhalt-Identität (Pflicht)
source_sha256_pinned   TEXT NOT NULL,      -- Hash zum Auswertungs-Zeitpunkt (Audit/Redundanz)
location_id            INTEGER,            -- Ablage-Kontext (optional, wenn relevant)
evaluated_at           TEXT NOT NULL
```

- `source_id` reicht für „welcher Inhalt"
- `source_sha256_pinned` ist Audit-Pin: zeigt im Klartext, welcher Hash gemeint
  war, robust gegen DB-Migrationen
- `location_id` nur wenn die Auswertung Ablage-spezifisch ist (z.B. DCC-
  Klassifikation hängt am „Geprüft"-Ordner)

### Validity-Check (eine Query)

```sql
SELECT 
  w.*,
  CASE
    WHEN s.status = 'deleted'                THEN 'stale_deleted'
    WHEN s.sha256 != w.source_sha256_pinned  THEN 'stale_replaced'
    ELSE 'valid'
  END AS validity
FROM workspace.work_X w
JOIN datastore.agent_sources s ON s.id = w.source_id;
```

Drei Zustände: `valid` / `stale_replaced` / `stale_deleted`. Mehr brauchen wir nicht.

### Stale-Politik

- Auswertungen werden NIE automatisch invalidiert oder gelöscht
- Auswertungen werden NIE automatisch auf neue Versionen migriert
- Disco zeigt Validity-Spalte in Reports, optional Onboarding-Hint
- User triggert Re-Run aktiv → neue Zeile mit neuem Pin, alte bleibt (Audit-Spur)

---

## Sync-Workflow

### Origin-Konzept

Jede `agent_source_locations`-Zeile trägt ein `origin`-Feld:
- `'sp-<libname>-full'` — Locations aus einem Full-Re-Snapshot einer SP-Library
- `'incr-<datum>'` — Locations aus einer Inkrement-Lieferung
- `'manual'` — manuell in sources/ abgelegt
- `'local-folder'` — initiale Migration (Bestandsdaten)

Damit kann die Pipeline pro Sync-Lauf wissen, welche locations zu welcher
Quelle gehören.

### Full-Re-Snapshot

User legt komplette SP-Library in einem Ordner ab, z.B. `sources/sp-rea-denox-full/`.
Der vorhandene Ordner-Inhalt wird ersetzt.

Pipeline-Algorithmus:
1. FS-Scan dieses Ordners → `(rel_path, sha256)` Set ist die Wahrheit
2. Pro FS-Eintrag:
   - Hash in `agent_sources` finden oder neu anlegen
   - Location-Match (rel_path + origin) finden oder neu anlegen
   - Wiederauferstehung, wenn nötig
3. Pro location mit `origin='sp-rea-denox-full'` UND `status='active'`,
   deren rel_path nicht im FS-Scan vorkommt → `status='deleted'`

→ **Lösch-Detection passiert implizit aus dem FS-Inhalt** — kein Manifest nötig.

### Inkrement-Lieferungen

User legt geänderte/neue Files in `sources/incr-<datum>/` ab.

Pipeline-Algorithmus:
1. FS-Scan dieses Ordners → additive Registrierung
2. KEINE Lösch-Detection — Inkremente sehen nur die Diffs, nicht das Soll

→ Zwischen Full-Re-Snapshots bleiben gelöschte SP-Files als `active` markiert,
bis der nächste Full sie nachzieht. Akzeptierter Trade-off.

### Wiederauferstehung — sauber spezifiziert

Wenn beim Scan eine Datei mit `(rel_path, sha256)` auftaucht, die als
location mit `status='deleted'` und gleichem `source_id` (= gleicher Hash) existiert:

1. **Kein Konflikt:** am gleichen rel_path ist keine andere `active` location
   → `status='active'`, `last_seen_at=now`. Markdown bleibt unverändert
   (Hash identisch, Inhalt identisch).
2. **Konflikt:** am gleichen rel_path existiert eine andere `active` location
   (Versions-Folge) → die alte bleibt `deleted`. Reasoning: an einem Pfad
   kann nur eine Datei aktiv sein.

---

## Migrations-Plan

### Phase 0: Backup (vor allem anderen)

Vor jeder Migration ein vollständiges Backup der DBs aller Prod-Projekte:

```bash
# Komprimierte Sicherung NUR der datastore.db + workspace.db
mkdir -p ~/Disco-backup-pre-pipeline-v2-2026-05-16
for proj in ~/Disco/projects/*/; do
  slug=$(basename "$proj")
  dest=~/Disco-backup-pre-pipeline-v2-2026-05-16/$slug
  mkdir -p "$dest"
  cp "$proj/datastore.db" "$dest/" 2>/dev/null
  cp "$proj/workspace.db" "$dest/" 2>/dev/null
  # Migrations-State + Meta
  cp -r "$proj/.disco" "$dest/" 2>/dev/null
done
```

Größe: ~1.6 GB total (DBs). Sources werden NICHT gesichert, weil
Migration sie nicht verändert.

### Phase 1: Trockenlauf auf DEV

1. `scripts/mirror_prod_project.sh <slug>` für mind. 2 Projekte (klein + groß)
   ins `~/Disco-dev/` ziehen
2. Migration-Script unter `migrations/project/datastore/NNN_pipeline_v2.sql`
   anlegen
3. Auf jedem gemirrorten Projekt durchlaufen lassen
4. Validierung:
   - Zeilen-Counts: unique sha256-Anteil korrekt?
   - Workspace-Pins: alle source_ids gemappt?
   - Markdown noch erreichbar?
   - Stichproben: 10 zufällige work_*-Einträge per Hand prüfen

### Phase 2: Schema-Migration (transaktional pro Projekt)

```sql
BEGIN TRANSACTION;

-- 1. Neue Tabellen anlegen (additiv, alt bleibt)
CREATE TABLE agent_sources_new (id, sha256 UNIQUE NOT NULL, ...);
CREATE TABLE agent_source_locations (id, source_id FK, rel_path, ...);

-- 2. Sources konsolidieren: eine Zeile pro unique sha256
INSERT INTO agent_sources_new (sha256, status, first_seen_at, last_seen_at,
                               markdown, markdown_meta, ...)
SELECT 
  sha256,
  CASE WHEN MAX(status='active') THEN 'active' ELSE 'deleted' END,
  MIN(first_seen_at), MAX(last_seen_at),
  -- Markdown von einer beliebigen aktiven Zeile (alle gleich, weil gleicher Hash):
  (SELECT md.md_content FROM agent_doc_markdown md WHERE md.source_hash = s.sha256 LIMIT 1),
  ...
FROM agent_sources s
WHERE sha256 IS NOT NULL
GROUP BY sha256;

-- 3. ID-Mapping erzeugen
CREATE TABLE _migration_source_id_map (old_id, new_id);
INSERT INTO _migration_source_id_map
SELECT old.id, new.id
FROM agent_sources old
JOIN agent_sources_new new ON new.sha256 = old.sha256;

-- 4. Locations befüllen: pro alte source-Zeile eine location-Zeile
INSERT INTO agent_source_locations
  (source_id, rel_path, origin, status, first_seen_at, last_seen_at, external_meta)
SELECT 
  m.new_id, old.rel_path,
  'local-folder',                   -- alle Bestandsdaten sind 'local-folder'
  old.status,
  old.first_seen_at, old.last_seen_at,
  json_object('sp_item_id', old.sp_item_id, 'sp_web_url', old.sp_web_url, ...)
FROM agent_sources old
JOIN _migration_source_id_map m ON m.old_id = old.id;

-- 5. agent_doc_markdown: file_id → source_id umbenennen (über Mapping)
UPDATE agent_doc_markdown 
SET file_id = (SELECT new_id FROM _migration_source_id_map WHERE old_id = file_id);

-- 6. agent_source_relations weg (Duplikate sind jetzt implizit)
DROP TABLE agent_source_relations;

-- 7. Rename: alt zu *_pre_migration, neu in Position
ALTER TABLE agent_sources RENAME TO agent_sources_pre_migration;
ALTER TABLE agent_sources_new RENAME TO agent_sources;

COMMIT;
```

### Phase 3: Workspace-Referenzen umbiegen

```python
# workspace.db ATTACH datastore.db AS ds
# Iteriere über alle work_*-Tabellen mit source_id-Spalten
for table in find_tables_with_source_id_column(workspace_db):
    cursor.execute(f"""
        UPDATE {table}
        SET source_id = (
          SELECT new_id 
          FROM ds._migration_source_id_map 
          WHERE old_id = source_id
        )
        WHERE source_id IS NOT NULL
    """)
```

**Risiko-Punkt:** Workspace-Einträge an Duplikat-Sources (z.B. 4.155 in
rea-denox) kollabieren jetzt auf die kanonische source_id. Wenn der User
für ein Duplikat und das Original getrennt klassifiziert hatte, kollidieren
die Annotationen. → Pro Projekt vor der Migration manuell prüfen, ob
Konflikte vorliegen, ggf. User-Entscheidung.

### Phase 4: Code-Anpassungen

Pipeline-Code muss neue Tabellenstruktur nutzen:
- `src/disco/agent/functions/sources.py` (sources_register, sources_detect_duplicates)
- `src/disco/agent/functions/data.py` (Queries)
- `src/disco/agent/functions/doc_markdown.py`
- `src/disco/flows/library/extraction*/runner.py`
- `src/disco/flows/library/extraction_routing_decision/runner.py`
- WebUI (Tree, File-Listing)

→ ein eigenes BL-Sub-Item, NACH erfolgreicher Schema-Migration.

### Phase 5: Prod-Rollout (Reihenfolge)

Pro Projekt: Backup → Migration → 24h beobachten → nächstes Projekt.

1. **bew-rsd-infrastruktur** (0 sources) — Smoke-Test, 0 Risiko
2. **vgb-referenzlisten** (113/113) — keine Duplikate, trivialer Fall
3. **bew-rsd-parkplaetze** (347/344) — fast keine Duplikate
4. **bew-rsd-lager-halle** (1.860/1.837)
5. **metadaten-prediction-opt** (1.905/1.882)
6. **bew-rsd-campus-reuter** (5.770/5.014)
7. **0-dcc-prediction-trainer** (13.280/8.276)
8. **bew-rsd-rea-denox** (6.018/1.907) — Stresstest, 68% Duplikat-Anteil

### Phase 6: Cleanup (nach 30 Tagen)

- `agent_sources_pre_migration` droppen
- `_migration_source_id_map` droppen
- `~/Disco-backup-pre-pipeline-v2-2026-05-16/` löschen

---

## Reversibilität — was wenn was schiefgeht?

| Was schief geht | Rollback |
|---|---|
| Schema-Migration scheitert mitten in Transaktion | `ROLLBACK` automatisch — kein Datenverlust |
| Migration scheint durch, aber falsche Daten erkannt | `ALTER TABLE agent_sources RENAME TO agent_sources_broken; ALTER TABLE agent_sources_pre_migration RENAME TO agent_sources;` + Backup-Restore |
| Workspace-Mapping kollabiert Annotationen falsch | Backup-Restore der workspace.db |
| Code-Bug in Pipeline-Code | Git-Revert auf vor-Migration-Commit + Backup-Restore |

**Sicherheitsnetze:**
- Backup vor jedem Projekt
- Migration ist transaktional
- alte Tabelle bleibt 30 Tage als `*_pre_migration`
- Validierungs-Stichproben nach jedem Projekt
- Reihenfolge: vom kleinsten zum größten

---

## Risiken + Mitigations

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| Workspace-Tabelle mit source_id übersehen | mittel | Migrations-Script findet `source_id`-Spalten dynamisch via `PRAGMA table_info` |
| Duplikat-Annotations-Kollision in rea-denox | hoch | Pre-Migration-Audit: prüfe `SELECT source_id, COUNT(DISTINCT ...) FROM work_*` |
| Markdown-Verlust bei Konsolidierung | niedrig | Test-Migration auf DEV, Stichproben |
| Foreign-Key-Verletzungen | niedrig | SQLite FK kann temporär deaktiviert werden während Migration |
| Performance bei rea-denox-Hashen | niedrig | Hashes sind alle schon da, kein Re-Hash nötig |
| User-Workflow muss neu gelernt werden | mittel | Sync-Workflow ist additiv, Bestandsdaten bleiben als `origin='local-folder'` |

---

## Verworfene Optionen (für die Akte)

- **`logical_document`-Entity**: User-Entscheidung 2026-05-15 — zu viel
  Struktur, möglichst flach. Versionen werden als delete+new behandelt.
- **`supersedes`-Pointer**: User-Entscheidung 2026-05-15 — würde implizite
  Versionierung erfordern, will der User nicht. Erkennt der User selbst
  am Pfad + Zeit.
- **`derived-from`-Relations** (DWG→PDF): User-Entscheidung 2026-05-16 —
  datastore.db speichert keine Datei-Beziehungen. Falls relevant: workspace
  als Annotation.
- **Manifest pro Sync**: User-Entscheidung 2026-05-16 — Full-Re-Snapshot
  reicht als implizites Manifest, kein zusätzlicher Pflege-Aufwand.

---

## Anhang: Bestandsdaten-Statistik (2026-05-16)

| Projekt | sources | unique hashes | dup-relations | markdown |
|---|---|---|---|---|
| 0-dcc-prediction-trainer | 13.280 | 8.276 | 5.004 | 7.147 |
| bew-rsd-campus-reuter | 5.770 | 5.014 | 756 | 4.379 |
| bew-rsd-rea-denox | 6.018 | **1.907** | 4.155 | 2.384 |
| bew-rsd-lager-halle | 1.860 | 1.837 | 23 | 1.822 |
| metadaten-prediction-opt | 1.905 | 1.882 | 0 | 1.671 |
| bew-rsd-parkplaetze | 347 | 344 | 3 | 339 |
| vgb-referenzlisten | 113 | 113 | 0 | 1 |
| bew-rsd-infrastruktur | 0 | 0 | 0 | 0 |

---

## Prod-Rollout 2026-05-16 — Bilanz

Alle 8 Projekte sauber migriert (klein → groß), alle Konsistenz-Checks
grün. Hash-Reform-Hebel besonders sichtbar bei:

- **bew-rsd-rea-denox**: 6.018 → 1.907 (68% Duplikat-Anteil)
- **0-dcc-prediction-trainer**: 13.280 → 8.276 (38%)
- **bew-rsd-campus-reuter**: 5.770 → 5.014 (13%)

Migrations-Runtime: 3-6 Sekunden pro Projekt.

Foundry-Portal-Agent: `disco-prod-agent` v91 mit 43 Tools (inkl. dem
neuen `verify_workspace_validity`).

---

## Cleanup-Roadmap (~30 Tage nach Rollout)

Nach 30 Tagen stabilem Betrieb können folgende Reste entfernt werden:

### Migrations-Reste in den DBs (pro Projekt)
```sql
DROP TABLE IF EXISTS agent_sources_pre_migration;
DROP TABLE IF EXISTS _migration_source_id_map;
VACUUM;
```
→ ca. 20-30 MB über alle 8 Projekte freigegeben.

### Backups (~3.2 GB)
- `~/Disco-backup-pre-prod-migration-20260516_231244/` (1.6 GB)
- `~/Disco-backup-pipeline-v2-rollout/` (1.6 GB)

### Alt-Schema-Code (Hygiene)
Sind defensive Fallbacks für nicht-migrierte Projekte — gibt es nach
Cleanup-Frist nicht mehr.

- `src/disco/agent/functions/sources.py`:
  - `_scan_one_scope` (alte Variante)
  - `_sync_pdf_inventory` (alte Variante)
  - `is_v2`-Dispatch-Logik in `_sources_register`
- `src/disco/agent/functions/fs.py`:
  - `has_locations`-Schema-Detection im canonical_path-Lookup

### Optional — regular migration für frische Projekte
Neue Projekte via `disco project init` starten aktuell mit dem alten
Schema (Migrationen 001-012). Bis das per regulärer Migration
`013_pipeline_v2.sql` abgedeckt ist, müsste man bei frischen Projekten
manuell `scripts/migrate_to_pipeline_v2.sh` aufrufen. In der Praxis
gerade unkritisch (keine neuen Projekte), aber Hygiene-Punkt.

### Optional — Pipeline-Runner Pin-Schreibung
Die Pipeline-Flows (`extraction_routing_decision` + `extraction`)
schreiben `source_sha256_pinned` und `evaluated_at` aktuell NICHT mit.
Neue `work_extraction_routing`-Einträge haben `no_pin`. Kein
funktionales Problem — die Pin-Konvention ist primär für vom Agent
geschriebene Auswertungen gedacht. Für Konsistenz wäre es sauber, die
Runner anzupassen (2-3 Zeilen pro Runner).

### Reihenfolge
1. Tag 30: Check ob Pipeline-Reform-v2 noch offene Probleme hat
2. DROP-Statements + VACUUM pro Projekt
3. Backups löschen (3.2 GB)
4. Alt-Schema-Code raus
5. Optional: 013_pipeline_v2.sql für künftige Projekte
6. Optional: Runner-Pin-Schreibung
7. Pipeline-Reform-v2-Hauptitem auf Done setzen

### Risiko
- DROP-Statements: harmlos, aber Rollback ab dann nicht mehr möglich
- Backup-Löschen: irreversibel
- Code-Cleanup: rein Hygiene, kein Funktions-Risiko
