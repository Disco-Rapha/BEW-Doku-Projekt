# Memory-Reform — Konzept

**Stand:** 2026-05-09
**Status:** Konzept abgenommen, Implementierung folgt in 6 Phasen
**Eingestuft:** Kritisch — entscheidet, wie effektiv Disco arbeitet,
wie häufig er halluziniert, wie gut er Projekte über Monate
verwalten kann, wie effektiv er Tools benutzt.

---

## 1) Warum diese Reform — Status quo gemessen

### 1.1 Memory-Größen in den drei aktiven Prod-Projekten

| Projekt | README | NOTES | **DISCO** | manifest |
|---|---:|---:|---:|---:|
| **lager-halle** | 6,6 KB | 42 KB | **56 KB / 49 H2-Kapitel** | 8,8 KB |
| rea-denox | 1,1 KB | 5,5 KB | 14 KB / 23 H2 | 1,8 KB |
| campus-reuter | 0,6 KB | 7,4 KB | 5,7 KB / 7 H2 | 1,0 KB |

`lager-halle` ist der kritische Fall: 56 KB DISCO.md mit 49 Kapiteln
— viele davon chronologische Sessions („HTML-Report Wochenbericht
2026-04-29", „Bautechnik Roh-IBL Vollabdeckung 2026-05-06"). Wir
nennen das **Wissens-Friedhof**: aufgesammelt, aber nicht aktiv
ansprechbar.

### 1.2 memory_read-Aufrufe in 30 Tagen

| Projekt | Total | **Default (8 KB)** | section() | tail | headings_only | full |
|---|---:|---:|---:|---:|---:|---:|
| lager-halle | 169 | **132 (78 %)** | 8 | 10 | 0 | 0 |
| rea-denox | 52 | **51 (98 %)** | 0 | 1 | 0 | 0 |
| campus-reuter | 38 | **35 (92 %)** | 0 | 1 | 1 | 0 |

→ Die am 2026-05-07 eingebauten 4 Modi (`headings_only`, `section`,
`tail`, `max_bytes`) werden in der Praxis fast nie gerufen. Der
System-Prompt führt Disco nicht ausreichend dorthin.

### 1.3 Drei harte Befunde

**Befund A — Wissens-Verlust durch zu rigorosen Default.**
Bei lager-halle lädt der Default 8 KB von DISCO.md. Diese 8 KB
enthalten *Aktueller Fokus / Konventionen / Projekt-Tabellen /
Lookup-Pfade / Glossar / Entscheidungen* + Anfang von *„Kontext:
Discoverse-Prediction-Feed"*. **Die anderen 42 Kapitel bleiben
unsichtbar.** Wenn Disco die KKS-Masterliste oder die Bautechnik-
IBL-Daten braucht, sieht er sie nicht — antwortet ohne sie oder
rät. Das **erklärt, warum Disco in lager-halle so viele Tool-Calls
macht** und warum trotzdem manche Antworten unscharf werden.

**Befund B — Unkontrollierter Token-Sockel pro Turn.**
169× memory_read × ~8 KB = **~1,3 MB Tokens in 30 Tagen** allein
für Memory-Reads in lager-halle. Plus pro Turn rund 25–30 k Tokens
nur für Chat-Verlauf-Recovery (gemessen am 2026-05-08). Sägezahn
zwischen Compactions liegt zwischen 65 k (direkt nach) und 198 k
(vor nächster Compaction).

**Befund C — Tabellen-Wissen schlecht platziert.**
Das Kapitel `## Projekt-Tabellen` in DISCO.md ist eine
Liste-mit-Beschreibung. Bei jedem Schema-Change muss Disco diese
Liste händisch updaten. Cross-Tabellen-Reasoning („welche Tabellen
haben einen KKS-Bezug?") funktioniert nur über DISCO.md-
Volltextsuche, nicht semantisch.

### 1.4 Was wir gewinnen wollen, was bleiben muss

**Output-Qualität bleibt mindestens gleich, eher besser.**
Konkret bedeutet das:

- Disco muss Antworten weiterhin durch Tool-Belege absichern.
- Disco darf bei Wissenslücken nicht halluzinieren — er soll sie
  benennen.
- Disco-Kapitel-Wissen muss aktiv verfügbar sein, wenn ein Thema
  angesprochen wird.

**Wir optimieren** auf:

- **Token- und Context-Effizienz** (Sockel runter, weniger
  Verschwendung).
- **Längere Projekt-Lebenszeit** (DISCO.md wird über Monate
  groß — muss skalieren).
- **Geschwindigkeit** (weniger Tool-Calls für gleichen Job, weil
  Disco gleich das richtige Kapitel hat).
- **Beobachtbarkeit** (jeder Memory-Zugriff im Log, jede Suche
  nachvollziehbar).

---

## 2) Architektur — drei Schichten

### 2.1 Schicht 1 — *Always-loaded* (max ~3 KB / ~750 Tokens)

Der Block, den Disco bei *jedem* `memory_read` ohne Argumente liest.
Inhalt:

| Block | Pflicht | Inhalt |
|---|---|---|
| Projekt-Identität | ja | Name, 1-Satz-Zweck, Status |
| Aktueller Fokus | ja | 1–3 Zeilen, was läuft gerade, was als Nächstes |
| Konventionen | ja | Tabellen-Prefixes, Pfad-Konventionen, Sprach-/Stil-Notizen |
| **Kapitel-Index** | ja | Liste aller Schicht-2-Kapitel-Titel mit Tags, **ohne Body** |

**Physisch:** in `DISCO.md`, oben, abgegrenzt durch Marker
`<!-- DISCO-LAYER-1-END -->`. Alles oberhalb des Markers gehört zu
Schicht 1, alles darunter zu Schicht 2.

**Hartes Limit Schicht 1**: max **3 500 Bytes**. Wenn ein Projekt
mehr ansammelt, ist das ein Pflege-Anlass — Disco wird den User per
NOTES-Eintrag darauf hinweisen. Schicht 1 darf nicht aufquellen.

### 2.2 Schicht 2 — *On-demand-Kapitel* (10–80 KB total)

Alles, was nicht ständig in den Kontext muss:

- Glossar, Entscheidungen, Lookup-Tabellen-Erklärungen
- Wissens-Sammelstellen (KKS-Masterliste, VGB-Normbezeichnungen,
  Evidenzlisten)
- Chronologische Session-Notizen, die heute in DISCO.md stehen
  (HTML-Report-Iterationen, Bautechnik-Reviews etc.)

**Physisch:** in `DISCO.md` unter dem Layer-1-Marker, ein H2 pro
Kapitel mit chapter-meta-Block (siehe §3).

**Disco lädt Schicht 2 nur per `memory_read({chapter: "..."})`**.
Default lädt sie nicht.

### 2.3 Schicht 3 — *Tabellen-Wissen am Tabellen-Objekt*

Die Tabelle `agent_table_docs` in `workspace.db`. Pro Projekt-Tabelle
(`work_*`/`agent_*`/`context_*`) ein Eintrag mit Beschreibung,
Schema-Summary, Beispiel-Query, Quell-Files. Disco fragt mit
SQL — nicht aus DISCO.md.

→ Schicht 3 ist **vollständig getrennt** von DISCO.md/NOTES.md.

### 2.4 NOTES.md — Chronik mit Auto-Archiv

- NOTES.md bleibt append-only Logbuch wie heute.
- **30-Tage-Schwelle**: Einträge älter als 30 Tage wandern beim
  Compaction-Event nach `.disco/notes-archive/<jahr-monat>.md`.
- Aktuelle NOTES.md wird dadurch klein gehalten (~5 KB).
- Disco kann Archiv mit `memory_read({file: "NOTES.md", chapter:
  "Archiv 2026-04"})` oder direkt per `fs_read` ansteuern.

---

## 3) Datenmodell — Markdown jetzt, SQL später (1:1-Mapping)

### 3.1 Schicht-2-Kapitel-Format (Markdown, ab heute)

```markdown
## Bautechnik IBL Roh-Stand
<!-- chapter-meta:
  tags: [bautechnik, ibl, soll-ist]
  created: 2026-05-06
  last_referenced: 2026-05-08
  status: current
-->

[Body bis zum nächsten H2 …]
```

**Pflichtfelder im chapter-meta-Block:**

- `tags`: Liste, Lower-case, Bindestrich-getrennt für Mehrwort-Tags
- `created`: ISO-Datum (`YYYY-MM-DD`)
- `last_referenced`: ISO-Datum, vom Tool gepflegt
- `status`: `current` | `archived` | `deprecated`

Das Format ist **strikt** und wird vom memory_read-Tool geparst.
Falsch formatierte Blöcke werden mit `chapter-meta-malformed`
geloggt, Kapitel ist trotzdem lesbar (Body-Match auf H2 reicht).

### 3.2 Spätere SQL-Form — `agent_memory_chapters`

```sql
CREATE TABLE agent_memory_chapters (
  chapter_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  title           TEXT NOT NULL UNIQUE,
  body            TEXT NOT NULL,
  tags_json       TEXT NOT NULL DEFAULT '[]',
  status          TEXT NOT NULL DEFAULT 'current'
                  CHECK (status IN ('current', 'archived', 'deprecated')),
  created_at      TEXT NOT NULL,            -- ISO-Datum
  last_referenced_at TEXT,                  -- ISO-Datetime, von Tool gepflegt
  reference_count INTEGER NOT NULL DEFAULT 0,
  updated_at      TEXT NOT NULL
);

CREATE INDEX idx_chapters_status ON agent_memory_chapters(status);
```

**1:1-Migration** Markdown → Tabelle:

| Markdown | SQL-Spalte |
|---|---|
| H2-Heading-Text | `title` |
| Body bis nächstem H2 | `body` |
| `tags`-Liste im chapter-meta | `tags_json` |
| `status` im chapter-meta | `status` |
| `created` im chapter-meta | `created_at` |
| `last_referenced` im chapter-meta | `last_referenced_at` |

**Migrations-Skript** (~80 Zeilen Python): Markdown-Parser → Insert.
Das erlaubt später einen sauberen Wechsel ohne Daten-Verlust und
ohne dass Disco's Verhalten anpassen muss.

### 3.3 Schicht-3 — `agent_table_docs`

```sql
CREATE TABLE agent_table_docs (
  table_name      TEXT PRIMARY KEY,
  layer           TEXT NOT NULL
                  CHECK (layer IN ('workspace', 'datastore', 'context')),
  description     TEXT NOT NULL,            -- 1-3 Zeilen
  schema_summary  TEXT,                     -- "kks_code TEXT PK, status TEXT, ..."
  example_query   TEXT,                     -- "SELECT * FROM ... WHERE ..."
  source_files    TEXT,                     -- "imported from sources/_meta/..."
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
```

Pflege per Tools:

- `table_doc_set(table_name, layer, description, schema_summary?,
  example_query?, source_files?)` — `INSERT OR REPLACE`
- `table_doc_get(table_name)` — Single-Row-Lookup

System-Prompt-Regel:

> *„Beim Anlegen einer neuen Tabelle pflegst Du `agent_table_docs`
> direkt mit (`table_doc_set`). Beim Reasoning auf einer
> bestehenden Tabelle holst Du Dir mit `table_doc_get` die
> Beschreibung, falls Du die Tabelle nicht selbst gerade erst
> angelegt hast."*

---

## 4) Tool-Spec — `memory_read` neu

### 4.1 Signatur (erweitert gegenüber heute)

```python
memory_read(
    file: "README.md" | "NOTES.md" | "DISCO.md",
    *,
    chapter: str | None = None,        # NEU — Kapitel-Title-Match (Substring, case-insensitive)
    headings_only: bool = False,
    tail: int | None = None,
    max_bytes: int | None = None,      # 0 = full
    # Default: liefert Schicht 1 (DISCO.md), kompletten File (README, NOTES klein)
)
```

### 4.2 Verhalten — Modus-Auswahl

Präzedenz, von oben nach unten:

| Wenn | Aktion |
|---|---|
| `chapter="..."` gesetzt | Sucht Schicht-2-Kapitel mit passendem Titel (case-insensitive Substring). Bei Hit: Body + chapter-meta. Bei Miss: `{found: false, chapter_index: [...]}` (Liste verfügbarer Titel). |
| `headings_only=True` | Liefert die Heading-Struktur als Outline. Schicht-1 + Schicht-2 separat ausgewiesen. |
| `tail=N` | Letzte N Zeilen — vor allem für NOTES.md. |
| `max_bytes=N` (>0) | Erste N Bytes — Power-User-Override. |
| `max_bytes=0` | Komplett — explizites Opt-out. |
| **kein Argument (Default)** | DISCO.md: nur Schicht 1 + Kapitel-Index. README.md: voll. NOTES.md: aktuelle (nicht-archivierte). |

### 4.3 Marker-Awareness in DISCO.md

Tool sucht den Marker `<!-- DISCO-LAYER-1-END -->`. Verhalten:

- **Marker gefunden:** Schicht 1 = bytes vor Marker (max 3 500).
  Schicht 2 = bytes nach Marker.
- **Marker fehlt** (alte DISCO.md): **Fallback wie heute** —
  Default liefert ersten 8 KB-Block. Disco-Verhalten unverändert.
  Damit ist die Reform abwärtskompatibel zu allen drei Prod-
  Projekten in ihrem heutigen Zustand.

### 4.4 Default-Antwort enthält den Kapitel-Index

Wenn Marker da ist, liefert Default:

```
[Schicht-1-Inhalt aus DISCO.md, max 3 500 Bytes]

---

# Verfügbare Kapitel (Schicht 2)

- "Bautechnik IBL Roh-Stand" [bautechnik, ibl, soll-ist]
- "KKS-Masterliste Lagerhalle 2026-04-28" [kks, masterliste]
- "VGB-Kern plus Praxis-Ergänzungen" [vgb, normen]
- "HK3-Bild-Evidenzen 2026-04-29" [evidenz, hk3]
- ...

# Hinweis
Lade konkretes Kapitel mit memory_read({chapter: "Titel-Substring"}).
```

→ Disco sieht beim Onboarding sofort, **was es alles gibt**, und
weiß welcher Begriff zu welchem Kapitel führt.

### 4.5 chapter-Match-Algorithmus (Hit-Strategie)

Pseudo-Code:

```
def find_chapter(chapters, query: str):
    q = query.lower().strip()

    # 1. Exakter Title-Match
    for c in chapters:
        if c.title.lower() == q:
            return c, "exact"

    # 2. Substring im Title (häufigster Fall)
    matches = [c for c in chapters if q in c.title.lower()]
    if len(matches) == 1:
        return matches[0], "substring"
    if len(matches) > 1:
        # Mehrere — der mit dem kürzesten Titel ist meist gemeint
        matches.sort(key=lambda c: len(c.title))
        return matches[0], "substring-multi"

    # 3. Tag-Match
    matches = [c for c in chapters if q in [t.lower() for t in c.tags]]
    if matches:
        return matches[0], "tag"

    # 4. Body-Volltext (last resort, weniger zuverlässig)
    for c in chapters:
        if q in c.body.lower():
            return c, "body"

    return None, "miss"
```

→ Bei Multi-Match wird das gewählt; im Result-Summary steht der
Match-Modus (`exact`/`substring`/`tag`/`body`/`miss`), damit später
ausgewertet werden kann, welche Heuristik trifft wie oft.

### 4.6 Side-Effect: `last_referenced` aktualisieren

Bei jedem erfolgreichen Kapitel-Hit wird der Meta-Block des Kapitels
aktualisiert:

- `last_referenced: 2026-05-09` (neues Datum)
- `reference_count` inkrementiert (neues Feld, wird beim ersten
  Update angelegt — `0` wenn nicht da)

Damit haben wir später Statistik: welche Kapitel werden nie geladen
und können archiviert werden? Disco kann beim periodischen Aufräumen
solche Kapitel mit `status: archived` markieren — bleiben physisch
da, fallen aber aus dem Default-Index raus.

---

## 5) Tracebarkeit — wie wir beobachten was Disco tut

### 5.1 Log-File `.disco/memory-access.log`

TSV-Format, append-only, eine Zeile pro Memory-Zugriff:

```
ts                       mode             file        chapter_query           hit_type     bytes  reference_count  message_id
2026-05-09T10:14:22Z     default          DISCO.md    -                       -            3072   -                421
2026-05-09T10:14:25Z     chapter          DISCO.md    "Bautechnik IBL"        substring    4810   3                421
2026-05-09T10:14:31Z     chapter          DISCO.md    "Verzogene Beton"       miss         0      0                421
2026-05-09T10:14:32Z     headings_only    DISCO.md    -                       -            1840   -                421
```

**Live-Beobachtung:** `tail -f .disco/memory-access.log` zeigt im
Terminal, was Disco gerade lädt und sucht. Bei Bug-Diagnose
*„Disco hat das Kapitel nicht gefunden"* → klar im Log sichtbar
welcher Query gestellt wurde und welcher hit_type kam.

### 5.2 Strukturiertes `result_summary` in `agent_tool_calls`

Heute speichert `agent_tool_calls.result_summary` einen freien String.
Für `memory_read` wird das ein JSON-Objekt:

```json
{
  "file": "DISCO.md",
  "mode": "chapter",
  "chapter_query": "Bautechnik IBL",
  "hit_type": "substring",
  "matched_title": "Bautechnik IBL Roh-Stand",
  "bytes": 4810,
  "reference_count_after": 3
}
```

Damit auswertbar:

```sql
-- "Welche Kapitel-Queries hat Disco im letzten Monat nicht gefunden?"
SELECT json_extract(result_summary, '$.chapter_query') AS query,
       COUNT(*) AS n
FROM agent_tool_calls
WHERE tool_name = 'memory_read'
  AND project_slug = 'bew-rsd-lager-halle'
  AND created_at >= datetime('now', '-30 days')
  AND json_extract(result_summary, '$.hit_type') = 'miss'
GROUP BY query
ORDER BY n DESC;
```

### 5.3 NICHT heute — UI-Memory-Widget

Kleines Sidebar-Panel *„Memory-Zugriffe in dieser Session"* wäre
Phase 7. Für jetzt reichen Log + DB-Auswertbarkeit fürs Debugging.

---

## 6) Migrations-Plan

### 6.1 Phasen-Übersicht

| Phase | Was | Aufwand | Migrations-Risiko | Reversibel? |
|---|---|---:|---|---|
| **P1** | `memory_read` mit Marker + `chapter`-Param + Trace-Log. Fallback ohne Marker = altes Verhalten. | 3 h | **null** — abwärtskompatibel | ja, einfacher Code-Revert |
| **P2** | `agent_table_docs` Tabelle + 2 Tools. System-Prompt-Regel ergänzt. | 2 h | klein — neue Tabelle, keine Daten überschrieben | ja |
| **P3** | NOTES-Archiv-Trigger im Compaction-Event. Erstes Archiv läuft bei nächster Compaction. | 1,5 h | mittel — Daten werden verschoben, aber ins selbe FS | ja, manuell zurückkopieren |
| **P4** | Migrations-Skript `migrate_disco_md.py` (Markdown-Parser → neuer Aufbau, mit Backup). Pro Projekt User-Review. | 4 h Tool + 1 h Review pro Projekt | mittel — User reviewt vor Commit | ja, Backup-File |
| **P5** | Initial-Befüllung `agent_table_docs` aus heutigem `## Projekt-Tabellen`-Kapitel pro Projekt. Halb-automatisch. | 1 h pro Projekt | klein | ja, DELETE FROM Tabelle |
| **P6** | (später) SQL-Migration `agent_memory_chapters` aus DISCO.md. Erst, wenn das Markdown-Modell ausgereift ist und der User explizit will. | 1 Tag | mittel | ja, Tabelle droppen |

### 6.2 Risiko-Mitigation pro Phase

**P1 — Tool-Erweiterung:**

- Neue Felder/Modi sind opt-in. Default-Verhalten bleibt identisch
  bis Marker da ist.
- Bei Parse-Fehler (kaputter chapter-meta-Block) → Kapitel ist
  trotzdem über Heading auffindbar, Meta-Felder fallen back auf
  Defaults.
- Trace-Log-File-Schreiben darf nicht crashen — Tool catched
  IOError, loggt einmal und macht weiter.

**P3 — NOTES-Archiv:**

- Atomic move via `tmp + rename`, nicht in-place-Truncate.
- Idempotent: re-run mit gleichem Schwellen-Datum produziert kein
  Doppel-Archiv.
- Vor jeder Archivierung wird NOTES.md.before-archive.bak im
  `.disco/`-Ordner abgelegt (überschrieben pro Lauf, aber 1 Backup
  immer da).

**P4 — DISCO.md-Migration:**

- Migrations-Skript hat **Dry-Run-Modus**: zeigt Diff, schreibt
  nichts. User reviewt.
- **Automatisches Backup** vor Commit: `DISCO.md.before-reform.bak`.
- **Heuristik dokumentiert**: welche heutigen Kapitel kommen in
  Schicht 1, welche bleiben in Schicht 2. Standard:
  - Schicht 1 (max 3,5 KB Pflicht): *Aktueller Fokus*,
    *Konventionen*, *Lookup-Pfade* (kondensiert), *Glossar*
    (kondensiert).
  - Schicht 2: alle anderen Kapitel, mit erstem chapter-meta-Block
    (`status: current`, `created` aus letztem mtime, `tags` per
    Heuristik aus Titel-Wörtern).
  - *Aktueller Fokus* aktualisiert auf den letzten NOTES-Eintrag.
- **Per-Projekt-User-Review**: Skript zeigt Diff, User akzeptiert
  oder editiert manuell, dann commit.

**P5 — `agent_table_docs`-Befüllung:**

- Initial-Befüllung läuft auf einer Kopie der Projekt-DB. Erst nach
  User-OK in die echte DB.
- `INSERT OR IGNORE` für Initial-Inserts — wenn ein Eintrag bereits
  existiert (manuelle Pflege), wird er nicht überschrieben.

### 6.3 Reihenfolge auf Prod-Projekten

P1 + P2 + P3 sind global — wirken auf alle Projekte gleichzeitig nach
Code-Deploy. P4 + P5 sind pro Projekt.

Vorgeschlagene Prod-Reihenfolge:

1. **rea-denox** (mittlere Größe, 23 Kapitel) — first.
2. **campus-reuter** (kleinste, 7 Kapitel) — Verifikation der
   Migration-Heuristik.
3. **lager-halle** (größtes, 49 Kapitel) — Last, weil heikelster
   Migration-Fall.

Begründung: rea-denox ist das beste Lerne-Stück (ausreichend
Kapitel, aber nicht so viele wie lager-halle). Wenn dort die
Heuristik solide läuft, ist lager-halle ein größeres aber kein
strukturell anderes Problem.

### 6.4 Backout-Plan

Wenn nach P1-P3 Probleme auftreten:

- Code-Revert: `git revert <commit>`. Disco-Agent setup neu.
- Marker in DISCO.md kann bleiben — Tool ohne den Code würde ihn
  ignorieren (er ist ein HTML-Kommentar, kein Markdown-Konstrukt).
- NOTES-Archiv-Files können ins NOTES.md zurück-konkateniert werden.

Wenn nach P4 (DISCO.md-Migration) Probleme:

- `.disco/DISCO.md.before-reform.bak` zurück nach `DISCO.md`
  kopieren.
- Disco arbeitet wieder mit dem alten Format (memory_read-Fallback
  ohne Marker).

---

## 7) Disco-Mind-Test — selbst-durchgeführter End-to-End-Test

Nach Implementierung von P1+P2+P3 (Tool-Ebene komplett) führe ich
auf **Dev** in `e2e-smoke-01` einen strukturierten Test durch. Das
Ziel: messen, ob die Reform die versprochene Wirkung bringt **ohne
die Output-Qualität zu reduzieren**.

### 7.1 Test-Aufbau

Vorab:

1. Frisches `e2e-smoke-01` aufsetzen mit `setup_e2e_project.sh`.
2. **Test-DISCO.md** anlegen mit Marker + 8 Schicht-2-Kapiteln, die
   thematisch passen zu den Test-Files (z.B. *„KKS-Masterliste"*,
   *„Bautechnik IBL"*, *„DCC-Klassen für Elektro"*, *„Lieferindex-
   Format"*).
3. `agent_table_docs` mit 3-4 Einträgen befüllen (Test-Tabellen).
4. Dev-Server reload, `disco agent setup --env dev`.

### 7.2 Sieben Test-Sequenzen

**T1 — Onboarding-Default**

Prompt: *„Hallo, das ist ein neues Test-Projekt. Magst Du Dich
kurz orientieren?"*

Erwartung:

- ✅ Disco ruft `memory_read({file: "DISCO.md"})` ohne Argumente.
- ✅ Result < 4 KB (Schicht 1 + Kapitel-Index).
- ✅ Antwort listet **Kapitel-Titel** ohne Body.
- ✅ Trace-Log: 1 Zeile mit `mode=default`, `bytes < 4 000`.

**T2 — Kapitel-Lookup auf Treffer (substring)**

Prompt: *„Wie ist der Stand bei der Bautechnik IBL?"*

Erwartung:

- ✅ Disco erkennt thematische Übereinstimmung mit Kapitel
  *„Bautechnik IBL Roh-Stand"*.
- ✅ Ruft `memory_read({chapter: "Bautechnik IBL"})`.
- ✅ Trace-Log: `hit_type=substring`, `matched_title="Bautechnik
  IBL Roh-Stand"`.
- ✅ Antwort enthält konkrete Inhalte aus dem Kapitel-Body, mit
  Quellen-Bezug.
- ✅ `last_referenced` im Meta-Block wurde auf heute aktualisiert.
- ✅ `reference_count` ist 1 oder höher.

**T3 — Kapitel-Lookup auf Miss**

Prompt: *„Was steht im Kapitel zum Schwerelosigkeit-Test?"*

Erwartung:

- ✅ Disco prüft Index, findet kein passendes Kapitel.
- ✅ Antwort: *„Es gibt kein Kapitel zu Schwerelosigkeit. Soll ich
  eines anlegen, wenn das Thema relevant wird?"*
- ✅ **Disco halluziniert keinen Inhalt.**
- ✅ Trace-Log: 1 Zeile mit `hit_type=miss`.

**T4 — Tag-Match**

Test-Kapitel hat Tag `[ibl, soll-ist]`. Prompt: *„Lade mir das
SOLL/IST-Wissen zur Bautechnik."*

Erwartung:

- ✅ Disco findet Kapitel über Tag-Match.
- ✅ Trace-Log: `hit_type=tag`.

**T5 — Token-Sockel-Vergleich**

Messung:

1. `measured_context_tokens` direkt nach Onboarding-Turn
   (post-reform).
2. Vergleich mit Vor-Reform-Wert aus dem Test am 2026-05-08
   (gemessen 91 k im e2e-smoke-01, danach in lager-halle real bis
   198 k angewachsen).

Erwartung:

- ✅ Onboarding-Turn-Sockel post-reform: < 50 k Tokens (vor reform
  ~91 k bei demselben Setup).
- ✅ Wachstumsrate pro nachfolgendem Turn: < 10 k Tokens (vor
  reform 5–21 k).

**T6 — Tabellen-Doc-Lookup**

Prompt: *„Was steht in `agent_dcc_results` drin? Welche Spalten?"*

Erwartung:

- ✅ Disco fragt `table_doc_get("agent_dcc_results")`.
- ✅ Antwort enthält Beschreibung + Schema-Summary + Beispiel-Query
  aus der `agent_table_docs`-Tabelle.
- ✅ Disco improvisiert nicht, falls die Tabelle dokumentiert ist.

**T7 — Rückkompatibilität (Marker fehlt)**

Setup: ein Test-Projekt mit alter DISCO.md ohne Marker (z.B.
`real-30-test`).

Erwartung:

- ✅ `memory_read` Default verhält sich wie heute: lädt 8 KB-Kopf.
- ✅ Kein Crash, kein Fehler.
- ✅ Trace-Log: 1 Zeile mit `mode=default`, kein chapter-Index in
  der Antwort.

### 7.3 Bewertung + Erfolgskriterium

**Pass-Bedingung:** alle 7 Tests grün, plus Token-Reduktion in T5
mindestens −40 % gegenüber Vor-Reform.

**Soft-Fail-Bedingung:** T2/T4 substring-Match scheitert wegen
ungewöhnlicher Wortwahl im Prompt. Mitigation: ich notiere die
Miss-Fälle, ergänze System-Prompt-Regel mit konkreten Triggern,
re-test.

**Hard-Fail-Bedingung:** T3 → Disco halluziniert Inhalt zu
nicht-existierendem Kapitel. Das wäre ein Reform-Stopper, weil
es die Output-Qualität verschlechtert. Sofortiger Backout.

### 7.4 Bericht-Format

Nach dem Test-Lauf schreibe ich einen Bericht in
`tests/e2e/scenarios/03-memory-reform.md` mit:

- Pro Test-Sequenz: ✅ pass / ⚠️ soft-fail / ❌ hard-fail.
- Trace-Log-Auszüge.
- Token-Sockel-Vergleich (gemessen vs. erwartet).
- Empfehlungen für nachträgliche System-Prompt-Anpassungen.

---

## 8) Erfolgs-Kriterien für die Reform insgesamt

**Quantitativ** (vor und nach 1 Woche Prod-Nutzung):

| Metrik | Vor | Ziel |
|---|---:|---:|
| memory_read default-Anteil | 95 % | < 70 % (Disco nutzt mehr Modi) |
| `chapter`-Use-Anteil | 0 % | > 30 % |
| Sockel pro Turn (lager-halle) | 65–198 k | 40–90 k |
| Tool-Calls pro Onboarding-Turn (lager-halle) | 110+ | < 30 |
| Halluzination bei Wissens-Frage (manuell stichprobenhaft) | gelegentlich | nie auf nicht-existente Kapitel |

**Qualitativ:**

- Disco identifiziert beim Onboarding aktive Kapitel und nennt sie
  beim Namen.
- Bei Themen-Frage holt er **das richtige Kapitel** beim ersten
  Versuch (gemessen über Trace-Log: `hit_type` ist
  `exact`/`substring` in > 80 % der Fälle).
- DISCO.md wächst kontrolliert: neue Erkenntnisse landen als neue
  Kapitel, nicht als Wischiwaschi-Anhängsel.
- Ältere Kapitel (`status: archived`) verschwinden aus dem Index
  ohne gelöscht zu werden.

---

## 9) Was wir in dieser Session NICHT machen (BACKLOG)

- **P6 SQL-Migration `agent_memory_chapters`**: erst, wenn das
  Markdown-Modell mindestens 3 Wochen Praxis-Erfahrung hat und der
  User das aktiv anstößt.
- **UI-Memory-Widget**: nice-to-have, später.
- **Kapitel-Auto-Tagging via LLM**: Disco könnte beim Anlegen
  neuer Kapitel automatisch Tags vorschlagen — heute manuell.
- **Cross-Projekt-Memory-Suche**: heute strikt projekt-lokal.

---

## 10) Anhang — Format-Beispiel: lager-halle DISCO.md nach Reform

**Vorher:** 56 KB, 49 H2-Kapitel, kein Marker, alles Default-geladen.

**Nachher (Skizze):**

```markdown
# DISCO.md — bew-rsd-lager-halle

## Projekt-Identität
Sanierung Lagerhalle BR_03 (BEW Demonstrations-Anlage), Doku-
Übergabe gegen VGB S 831. Aktive Phase: Mai 2026.

## Aktueller Fokus
Bautechnik-IBL-Übersichten finalisieren, KKS-Masterliste gegen
sources/ verifizieren, HTML-Wochenbericht für AG vorbereiten.

## Konventionen
- DCC-Codes Disco-eigen: `agent_dcc_*`
- Tabellen aus IBL-Excel: `context_ibl_*`
- HTML-Reports landen in `exports/reports/<slug>/`

## Lookup-Pfade
- KKS-Hierarchie: context_kks_hierarchy
- VGB-Klassen: context_vgb_dcc_codes
- Detail-Tabellen siehe agent_table_docs

<!-- DISCO-LAYER-1-END -->

## KKS-Masterliste Lagerhalle 2026-04-28
<!-- chapter-meta:
  tags: [kks, masterliste, lagerhalle]
  created: 2026-04-28
  last_referenced: 2026-05-08
  status: current
-->

[Body wie heute …]

## Bautechnik IBL Roh-Stand
<!-- chapter-meta:
  tags: [bautechnik, ibl, soll-ist]
  created: 2026-05-06
  last_referenced: 2026-05-08
  status: current
-->

[Body …]

## HTML-Report Wochenbericht 2026-04-29
<!-- chapter-meta:
  tags: [html-report, wochenbericht]
  created: 2026-04-29
  last_referenced: 2026-05-02
  status: archived
-->

[Body …]

[…42 weitere Kapitel mit Meta-Block, einige `status: archived`]
```

Schicht 1 hier: ~1,8 KB. Kapitel-Index zusätzlich: ~1,2 KB. Total
Default-Antwort: ~3 KB statt heute 8 KB. Plus Disco kennt jetzt alle
49 Kapitel by name.

---

**Stand des Konzepts:** abnahmebereit. Bei OK starte ich mit
Phase 1 (Tool-Erweiterung + Trace-Log). Phase 2 + 3 folgen heute.
Phase 4 + 5 (DISCO.md-Migration + table-docs-Befüllung pro
Prod-Projekt) machen wir gemeinsam, weil User-Review nötig.
