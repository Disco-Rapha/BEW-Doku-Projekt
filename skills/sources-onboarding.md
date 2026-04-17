---
name: sources-onboarding
description: sources/ registrieren, Begleit-Metadaten anhaengen, Duplikate erkennen. Pflegt die agent_sources-Registry.
when_to_use: "neue Quellen geladen", "registriere", "neuer SP-Export", oder wenn sources/ Dateien enthaelt die nicht in agent_sources stehen.
---

# Skill: sources-onboarding

Der Ordner `sources/` enthaelt **Arbeitsdokumente** — was analysiert,
bewertet, klassifiziert werden soll. Anders als `context/` (Arbeits-
grundlagen) ist hier das *Rohmaterial*.

Disco fuehrt eine **Registry** der Quelldateien in der Tabelle
`agent_sources`. Jede Datei hat einen SHA-256-Hash, den Status
`'active'`/`'deleted'`, Filesystem-Metadaten und optional Begleit-
Metadaten.

## Wann dieser Skill laeuft

- Neues Paket / Erstregistrierung: Benutzer hat gerade Dokumente nach
  `sources/` kopiert (z.B. SharePoint-Export entpackt).
- Nach-Registrierung bei aktualisiertem Paket: neuer SP-Export, einige
  Dateien neu, andere geaendert, manche weg.
- Verifikation: Benutzer fragt "wie viele Dokumente haben wir?" oder
  "was ist neu seit dem letzten Scan?".

## Verbindlicher Workflow

### 1. Zustand einschaetzen

```text
sqlite_query({"sql": "SELECT COUNT(*) AS active, (SELECT COUNT(*) FROM agent_sources WHERE status='deleted') AS deleted FROM agent_sources WHERE status='active'"})
sqlite_query({"sql": "SELECT scan_type, started_at, n_new, n_changed, n_deleted, n_unchanged FROM agent_source_scans ORDER BY id DESC LIMIT 3"})
```

Damit weisst Du:
- Wie viele aktive Dateien bereits registriert sind
- Ob jemals gescannt wurde, und wenn ja wann

### 2. Scan-Typ waehlen

Abhaengig vom Zustand:
- **0 Eintraege, kein Scan je gelaufen** → `scan_type='initial'`
- **Eintraege vorhanden, Benutzer spricht von neuem Paket** → `scan_type='incremental'` (Default) mit Label wie `'nach-sp-export-2026-04-17'`
- **Nur Sanity-Check ohne neue Dateien** → `scan_type='verify'`

### 3. Scan durchfuehren

```text
sources_register({"scan_type": "<typ>"})
```

Das Tool:
- Walkt `sources/` rekursiv (ausser `_meta/`)
- Berechnet SHA-256 fuer jede Datei
- Vergleicht mit `agent_sources`:
  - Pfad unbekannt → **neu**
  - Pfad bekannt, Hash anders → **geaendert**
  - Pfad in DB, Datei nicht mehr im FS → **geloescht**
  - Pfad + Hash identisch → **unveraendert**
- Schreibt einen Eintrag in `agent_source_scans`

### 4. Ergebnis interpretieren

Melde dem Benutzer in **max. 6 Zeilen**:

- Scan-Dauer + Gesamtzahl aktiver Dateien
- Kurz: `X neu, Y geaendert, Z geloescht, W unveraendert`
- Bei >0 neu: 2-3 Beispiel-Pfade nennen (aus `delta.new.sample`)
- Bei >0 geloescht: **immer** alle Pfade nennen (delete ist heikel, soll
  dem Benutzer nicht entgehen)
- Bei >0 geaendert: 2-3 Beispiele, und kurzer Hinweis: *"Bestehende
  Analysen auf diese Dateien sollten neu gelaufen werden."*
- Bei 0 Delta: *"Alles aktuell, kein Delta."*

### 5. Uebersicht pro Ordner (optional)

Wenn's ein grosses Paket ist (>100 neue Dateien), Gewerk-Uebersicht
anbieten:

```text
sqlite_query({"sql": "SELECT folder, COUNT(*) AS n FROM agent_sources WHERE status='active' GROUP BY folder ORDER BY n DESC LIMIT 20"})
```

Das hilft dem Benutzer zu sehen, wie sich das Paket auf die Gewerke
verteilt, ohne in den Filesystem-Explorer zu springen.

## Anschluss-Schritt 1: Begleit-Metadaten zuordnen

Wenn Du im Scan einen Ordner `sources/_meta/` entdeckt hast (oder der
Benutzer eine Begleit-Datei erwaehnt), folge diesem Zweistufen-Flow:

### Trockenlauf zuerst (commit=false)

```text
sources_attach_metadata({
  "path": "sources/_meta/sources-meta.xlsx",
  "key_column": "rel_path",
  "commit": false
})
```

(Die `key_column` heisst oft `rel_path`, kann aber auch `Dateiname`,
`Pfad`, `Datei` sein — schau kurz in die Datei, wenn unsicher.)

Der Trockenlauf liefert:
- `matched_exact` / `matched_filename`: wie viele Zeilen aufgeloest
- `ambiguous_total`: Filename taucht in mehreren Ordnern auf
- `not_found_total`: Pfad/Name nicht in der Registry

### Ergebnis bewerten

- Wenn `matched_exact == total_rows`: alles sauber → sofort commit.
- Wenn `not_found_total > 0`: liste die ersten paar auf. Meist ist es:
  - Tippfehler in der Excel
  - Datei wurde geloescht seit Excel-Erstellung
  - Pfad-Format weicht ab (Backslashes, sources/-Prefix)
- Wenn `ambiguous_total > 0`: Kandidaten pro Eintrag zeigen, Benutzer
  fragen welcher der richtige ist, **bevor** Du commit machst.

### Commit

```text
sources_attach_metadata({
  "path": "sources/_meta/sources-meta.xlsx",
  "key_column": "rel_path",
  "commit": true
})
```

Schreibt fuer jede gefundene Datei pro Spalte einen Eintrag in
`agent_source_metadata` (source_of_truth='begleit-excel'). Idempotent:
wiederholte Commits ueberschreiben bestehende Werte, dupliziert nichts.

### Abfrage spaeter

```sql
SELECT s.rel_path, m.key, m.value
FROM agent_source_metadata m
JOIN agent_sources s ON s.id = m.source_id
WHERE m.source_of_truth = 'begleit-excel'
  AND m.key = 'gewerk'
```

## Anschluss-Schritt 2: Duplikate erkennen

Nach dem Scan bietet sich fast immer an:

```text
sources_detect_duplicates({})
```

Das Tool gruppiert alle aktiven Dateien per sha256-Hash und legt pro
Duplikat-Set `duplicate-of`-Relationen an: der aelteste Eintrag
(ueber `first_seen_at`) wird **kanonisch**, die anderen zeigen auf ihn.

Rueckmeldung an den Benutzer:
- Wenn `groups_found == 0`: "Keine Duplikate gefunden."
- Wenn `groups_found > 0`: nenn die Zahl, und liste **bis zu 5**
  Beispiel-Sets (je 1 Zeile: `sha256[:8]...  kanonisch ← N Kopien`).
  Biete an: *"Wenn Du willst, kann ich die nicht-kanonischen Kopien
  auflisten damit Du entscheiden kannst, ob manche geloescht werden."*

### SQL fuer Duplikat-Uebersicht

```sql
SELECT c.rel_path AS kanonisch, s.rel_path AS kopie, r.detected_at
FROM agent_source_relations r
JOIN agent_sources s ON s.id = r.from_source_id
JOIN agent_sources c ON c.id = r.to_source_id
WHERE r.kind = 'duplicate-of'
ORDER BY c.rel_path, s.rel_path;
```

## Was Du NICHT tun sollst

- **Dateien nicht selbst loeschen.** `agent_sources.status='deleted'`
  ist ein Soft-Delete, das Tool macht das. Der Benutzer kann Dateien
  im FS selbst loeschen/zurueckholen.
- **Nicht fuer context/-Dateien verwenden.** `sources_register` scannt
  nur `sources/`. Fuer `context/` gibt es `context-onboarding`.
- **Keine Klassifikation beim Scan.** Der Scan registriert nur. DCC-
  oder Gewerks-Klassifikation kommt spaeter ueber Jobs (Phase 2c).

## Antwort-Vorlage

```
Scan durch (<dauer_s>s) — <total_active> aktive Dateien in der Registry.

Delta:
  + neu:       <n>  (Beispiele: ...)
  ~ geändert:  <n>  (Beispiele: ...)
  − gelöscht:  <n>  (alle: ...)
  · unverändert: <n>

Top-Ordner: <ordner>: <n>, <ordner>: <n>, ...

Was möchtest Du als Nächstes damit machen?
```
