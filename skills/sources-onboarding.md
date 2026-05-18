---
name: sources-onboarding
description: sources/ (und optional context/) registrieren, Begleit-Metadaten anhaengen, Duplikate erkennen. Pflegt die agent_sources-Registry + spiegelt PDFs ins agent_pdf_inventory.
when_to_use: "neue Quellen geladen", "registriere", "neuer SP-Export", oder wenn sources/ Dateien enthaelt die nicht in agent_sources stehen.
---

# Skill: sources-onboarding

Der Ordner `sources/` enthaelt **Arbeitsdokumente** — was analysiert,
bewertet, klassifiziert werden soll. Anders als `context/` (Arbeits-
grundlagen) ist hier das *Rohmaterial*.

Disco fuehrt eine **Registry** in der Tabelle `agent_sources`. Jede
Datei hat einen SHA-256-Hash, den Status `'active'`/`'deleted'`,
Filesystem-Metadaten, optional Begleit-Metadaten und ein
`kind`-Tag (`'source'` oder `'context'`), das die beiden Welten
sauber trennt — auch wenn sie durch dieselbe Registry + denselben
PDF-Pipeline-Weg laufen.

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
- Walkt den gewaehlten Scope-Root rekursiv (ausser `_meta/`).
  Default `scope='both'` scannt `sources/` UND `context/` nacheinander —
  in der Regel das Gewuenschte. Mit `scope='sources'` bzw.
  `scope='context'` schraenkst Du auf einen einzelnen Unterbaum ein.
- Berechnet SHA-256 fuer jede Datei
- Vergleicht mit `agent_sources`:
  - Pfad unbekannt → **neu**
  - Pfad bekannt, Hash anders → **geaendert**
  - Pfad in DB, Datei nicht mehr im FS → **geloescht**
  - Pfad + Hash identisch → **unveraendert**
- Schreibt einen Eintrag in `agent_source_scans`
- **Spiegelt PDFs nach `agent_pdf_inventory`** (mit `kind`-Tag), damit
  die Pipeline-Flows (`pdf_routing_decision`, `pdf_to_markdown`) sie
  sehen.

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
-- Metadaten zu einer Source (Inhalt-orientiert, alle Locations zusammen):
SELECT m.key, m.value, m.source_of_truth
FROM agent_source_metadata m
WHERE m.source_id = ? AND m.key = 'gewerk';

-- Mit Pfad-Anzeige (eine repräsentative Location):
SELECT 
  (SELECT rel_path FROM agent_source_locations 
   WHERE source_id = s.id AND status='active' LIMIT 1) AS rel_path,
  m.key, m.value
FROM agent_source_metadata m
JOIN agent_sources s ON s.id = m.source_id
WHERE m.source_of_truth = 'begleit-excel' AND m.key = 'gewerk';
```

## Anschluss-Schritt 2: Duplikate sind strukturell sichtbar

Seit Pipeline-Reform v2 (2026-05-16) ist Duplikat-Erkennung **kein
eigener Schritt mehr**. Im hash-zentrierten Datastore-Modell ergibt
sich aus den Locations pro Source automatisch:

```sql
-- Wie viele Inhalte haben mehrere Ablageorte (= sind dupliziert)?
SELECT COUNT(*) AS n_duplicated_contents
FROM (
  SELECT source_id, COUNT(*) AS n_locations
  FROM agent_source_locations
  WHERE status = 'active'
  GROUP BY source_id
  HAVING n_locations > 1
);
```

Wenn ein Inhalt an 32 Stellen liegt: eine `agent_sources`-Zeile + 32
`agent_source_locations`-Zeilen. Markdown läuft pro Hash **genau
einmal** — also auch keine doppelten Extraktionen, kein Aufräum-
Aufwand.

### Top-Duplikate anzeigen (wenn der Nutzer fragt)

```sql
SELECT 
  s.id, substr(s.sha256, 1, 12) AS hash,
  COUNT(l.id) AS n_locations,
  GROUP_CONCAT(l.rel_path, ' | ') AS paths
FROM agent_sources s
JOIN agent_source_locations l ON l.source_id = s.id AND l.status = 'active'
WHERE s.status = 'active'
GROUP BY s.id
HAVING n_locations >= 3
ORDER BY n_locations DESC
LIMIT 10;
```

Rückmeldung an den Benutzer beim Scan:
- Wenn nach `sources_register` mehrere Locations pro source entstanden
  sind: nenn die Top-3 mit der höchsten Anzahl Locations als Hinweis,
  ohne dramatisch zu werden ("Schon erwartet, das Hash-Modell handhabt
  das automatisch").
- Wenn der Nutzer aktiv aufräumen will: Liste der nicht-active Locations
  + Vorschlag welche physisch aus sources/ entfernt werden könnten.

**Achtung:** Bestandsprojekte aus der Zeit vor der Reform haben evtl.
noch `agent_source_relations` mit `kind='duplicate-of'`. Diese Tabelle
ist deprecated und wird durch die Schema-Migration gedroppt. Wenn Du
Code aus der Zeit findest, der darauf zugreift, sag dem Nutzer
Bescheid — das ist veraltet.

## Was Du NICHT tun sollst

- **Dateien nicht selbst loeschen.** `agent_sources.status='deleted'`
  ist ein Soft-Delete, das Tool macht das. Der Benutzer kann Dateien
  im FS selbst loeschen/zurueckholen.
- **Keine Klassifikation beim Scan.** Der Scan registriert nur. DCC-
  oder Gewerks-Klassifikation kommt spaeter ueber Jobs (Phase 2c).
- **Keinen eigenen Pfad fuer context/ bauen.** Auch Context-Dateien
  laufen ueber `sources_register` — einfach mit `scope='context'`.
  Fuer die inhaltliche Analyse + Summary-Pflege danach siehe den
  `context-onboarding`-Skill.

## Anschluss-Schritt 3: PDF-Pipeline vorschlagen (PFLICHT bei PDFs)

Der Return von `sources_register` enthaelt `pdf_inventory` mit der Anzahl
PDFs, die nach `ds.agent_pdf_inventory` (Ebene 2) gespiegelt wurden. Wenn
`pdf_inventory.total_inventory > 0`, MUSST Du dem Benutzer die
PDF-Pipeline aktiv vorschlagen — *nicht* nur als Hinweis am Ende,
sondern als klare Handlungsempfehlung mit Frage.

**Warum Pflicht:** Ohne Routing + Extraktion bleiben die PDFs im
Inventar, aber ihr Inhalt ist fuer Disco nicht lesbar. Das ist fuer den
Benutzer nicht selbsterklaerend — er sieht die Dateien registriert und
denkt "fertig". Ist er nicht.

**Formulierungsbeispiele** (waehle je nach Kontext):
- Erstregistrierung, groesseres Paket:
  *"Als Naechstes wuerde ich die PDF-Pipeline starten: erst
  `pdf_routing_decision` (entscheidet pro Datei welche Engine —
  docling lokal oder Azure DI), dann `pdf_to_markdown` fuer die
  eigentliche Text-Extraktion. Soll ich anfangen?"*
- Kleines Paket / wenige PDFs:
  *"Soll ich gleich das PDF-Routing + die Extraktion laufen lassen,
  damit der Inhalt lesbar wird?"*
- Benutzer hat `pdf_routing_decision` bereits manuell/frueher gemacht:
  *"Routing ist fuer X von Y PDFs schon gelaufen. Soll ich fuer die
  restlichen Z das Routing nachziehen und dann extrahieren?"*

**Ausnahmen:**
- Kein einziges PDF im Paket (`pdf_inventory.total_inventory == 0`) →
  kein Vorschlag, stattdessen generische Frage.
- Benutzer hat explizit gesagt "erst mal nur registrieren" → respektieren
  und nur kurz erwaehnen.

## Antwort-Vorlage

```
Scan durch (<dauer_s>s) — <total_active> aktive Dateien in der Registry.

Delta:
  + neu:       <n>  (Beispiele: ...)
  ~ geändert:  <n>  (Beispiele: ...)
  − gelöscht:  <n>  (alle: ...)
  · unverändert: <n>

Top-Ordner: <ordner>: <n>, <ordner>: <n>, ...

PDF-Inventar: <pdf_inventory.total_inventory> PDFs eingangsbereit.

Vorschlag: Als Naechstes `pdf_routing_decision` starten (Engine-Wahl pro
Datei), danach `pdf_to_markdown` fuer die Extraktion. Soll ich anfangen?
```

Falls keine PDFs im Paket sind:

```
Scan durch (<dauer_s>s) — ...

Keine PDFs dabei. Was moechtest Du als Naechstes damit machen?
```
