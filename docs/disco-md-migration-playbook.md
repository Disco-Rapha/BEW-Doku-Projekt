# DISCO.md Migration auf 3-Schichten-Format — Playbook

**Stand:** 2026-05-09. Beschreibt, wie ein bestehendes Projekt von der
Legacy-DISCO.md (eine flache Datei, 8-KB-Default-Cap) auf das
Reform-Format (Schicht 1 + chapter-meta-Kapitel) migriert wird.

**Hintergrund:** Die Memory-Reform (siehe ADR
`docs/architecture-decisions.md` 2026-05-09) hat das DISCO.md-Format
um einen Marker-basierten Schicht-Split erweitert. Projekte ohne
Marker funktionieren weiter (Legacy-Fallback), profitieren aber nicht
vom gezielten Kapitel-Lookup. Migration ist freiwillig pro Projekt.

---

## Wann lohnt sich die Migration?

| Indikator | Schwelle |
|---|---|
| DISCO.md-Größe | > 5 KB |
| Anzahl `## `-Sektionen | > 8 |
| Doppelte Header (`## Entscheidungen` mehrfach) | ≥ 2 Vorkommen |
| Token-Verbrauch pro Onboarding (aus Trace-Log) | > 4 KB |

Wenn 2 von 4 Indikatoren zutreffen: Migration empfohlen.
Bei < 5 KB Datei kann das Reform-Format auch sinnlos werden — Schicht 1
allein reicht.

---

## Vorgehen

### 1. Backup

**Nicht überspringen.** Das Backup ist der Sicherungs-Anker, falls die
Migration Inhalte verliert oder zusammenzieht.

```bash
cp ~/Disco/projects/<slug>/DISCO.md \
   ~/Disco/projects/<slug>/DISCO.md.backup-$(date +%Y-%m-%d)
```

### 2. Ist-Stand verstehen

```bash
# Header-Outline
grep -n "^## " ~/Disco/projects/<slug>/DISCO.md

# Größe + Zeilen
wc -lc ~/Disco/projects/<slug>/DISCO.md

# Doppelte Header
grep "^## " ~/Disco/projects/<slug>/DISCO.md | sort | uniq -c | sort -rn | head
```

Häufige Fundmuster:

- `## Entscheidungen` mehrfach → in **ein** chronologisches
  Entscheidungen-Log mergen
- `## SharePoint-Links` mehrfach → eine kanonische Aussage konsolidieren
- Veraltete Snapshots (z. B. „Stand 2026-04-26") → mit
  `status: archived` markieren, nicht löschen
- Leere Template-Platzhalter („*(Was steht gerade an? 1-3 Sätze.)*") →
  ersatzlos raus

### 3. Zielstruktur entwerfen

**Schicht 1 (≤ 3,5 KB) — gehört in jedes Projekt:**

- `## Projekt-Identität` (Wer/Was/Auftrag)
- `## Aktueller Fokus` (3–5 Bullets, was gerade ansteht)
- `## Konventionen` (harte Regeln, die immer gelten)
- `## Lookup-Pfade` (Tabellen, wichtige Files, Skript-Pfade)

**Marker direkt nach Lookup-Pfaden:**

```markdown
<!-- DISCO-LAYER-1-END -->
```

**Schicht 2 (on-demand-Kapitel):**

- Pro Themenfeld ein H2-Kapitel mit chapter-meta-Block:

```markdown
## KKS-Masterliste

<!-- chapter-meta:
  tags: [kks, masterliste]
  created: 2026-05-09
  status: current
-->

<Body-Inhalt>
```

- `tags` als Liste in lower-case (für Tag-Match in `memory_read`)
- `created` im Format `YYYY-MM-DD`
- `status`: `current` | `archived` | `deprecated`

**Tipp:** Veraltete Stände **nicht löschen**, sondern als eigenes
Kapitel mit `status: archived` behalten — sie zählen dann nicht ins
Default-Onboarding, sind aber per `chapter:`-Lookup weiter erreichbar.

### 4. Schreiben

Komplett überschreiben über `memory_write` (atomar, tmp+rename).
Marker `<!-- DISCO-LAYER-1-END -->` muss zwischen Schicht 1 und
Schicht 2 stehen.

```python
# über das Tool
memory_write({
  "file": "DISCO.md",
  "content": "<komplette neue Datei>"
})
```

Oder direkt im Filesystem (z. B. wenn du die Migration als Script
fährst — wie wir es am 2026-05-09 für die drei Prod-Projekte gemacht
haben).

### 5. Validierung

**Schicht 1 unter dem Cap:**

```bash
awk '/<!-- DISCO-LAYER-1-END -->/{exit} {print}' \
  ~/Disco/projects/<slug>/DISCO.md | wc -c
```

Muss < 3500 sein. Wenn drüber: Lookup-Pfade trimmen (Detail in
spezielle Kapitel verlagern), Konventionen straffen.

**Kapitel-Outline:**

```bash
grep -n "^## " ~/Disco/projects/<slug>/DISCO.md
```

Sollte sauber lesen — keine Doppel-Header mehr.

**Verloren-Check** (Schlüsselbegriffe aus dem Backup gegen die neue
Datei prüfen):

```bash
for term in "<wichtiger-Tabellenname>" "<Personenname>" \
            "<Skript-Pfad>" "<Kürzel>"; do
  cnt=$(grep -c "$term" ~/Disco/projects/<slug>/DISCO.md)
  [ "$cnt" -eq 0 ] && echo "MISSING: $term"
done
```

Liste der Schlüsselbegriffe aus dem Backup ableiten —
typischerweise: alle `agent_*`-Tabellennamen, alle erwähnten Personen,
alle Lookup-File-Pfade, alle erwähnten Excel-Snapshots.

### 6. Live-Test

Im Browser das Projekt öffnen, frische Chat-Session, Onboarding-Frage
stellen:

> "Hallo, magst Du Dich kurz orientieren?"

Erwartet: Disco lädt nur Schicht 1 + Index (~2,5–3,5 KB), nennt die
Themenfelder, fragt nicht nach Inhalten.

Folgefrage zu einem konkreten Kapitel-Thema:

> "Was ist eigentlich der Stand bei <Kapitel-Thema>?"

Erwartet: gezielter `chapter`-Aufruf im Trace-Log
(`.disco/memory-access.log`).

### 7. Trace-Log reviewen

```bash
cat ~/Disco/projects/<slug>/.disco/memory-access.log
```

Die ersten Zeilen nach der Migration zeigen, wie das Onboarding läuft:
sollte `default DISCO.md` mit < 3,5 KB plus 1–2 gezielte
`chapter`-Hits sein, nicht 8 KB Voll-Read.

---

## Häufige Stolperfallen

- **Schicht 1 quillt auf** — Lookup-Pfade haben einen großen Pull. Wenn
  > 3,5 KB: Pfade in spezielle Kapitel verlagern, in Schicht 1 nur die
  ~5–8 wichtigsten lassen.
- **Marker fehlt in der neuen Datei** → Default-Read fällt auf
  Legacy-8-KB zurück. Nach `memory_write` mit `grep` prüfen.
- **chapter-meta-Block direkt unter dem Heading, ohne Leerzeile dazwischen** —
  funktioniert; aber die automatische Side-Effect-Aktualisierung
  (`last_referenced`/`reference_count`) kollabiert die Leerzeile zwischen
  `-->` und Body. Kosmetisch, kein Funktionsfehler. Backlog-Eintrag.
- **Tags falsch geschrieben** — `tags: [KKS]` statt `tags: [kks]`. Match
  ist case-sensitive über den geparsten YAML; immer lower-case.
- **Status-Werte außerhalb der Whitelist** — nur `current`,
  `archived`, `deprecated` sind anerkannt; andere Werte werden ignoriert.

---

## Beispiele aus der Praxis

Drei Prod-Projekte wurden am 2026-05-09 nach diesem Playbook migriert:

| Projekt | DISCO vorher | DISCO nachher | Schicht 1 | Kapitel |
|---|---:|---:|---:|---:|
| `bew-rsd-rea-denox` | 14 KB | ~17 KB strukturiert | 2,2 KB | 10 |
| `bew-rsd-campus-reuter` | 5,7 KB | ~6 KB strukturiert | 2,4 KB | 6 |
| `bew-rsd-lager-halle` | 56 KB | 34 KB | 3,3 KB | 13 |

Das größte Konsolidierungspotenzial bei `lager-halle`: 5× KKS-Sektionen
zu einem Kapitel + 8× Bautechnik-Sektionen zu einem Kapitel + 10×
HTML-Report-Sektionen zu einem Kapitel. Die meisten Token-Einsparungen
liegen genau in solchen über-Wochen-gewachsenen Themen-Clustern.

---

## Pointer

- **Tool-Implementierung:** `src/disco/agent/functions/memory.py`
  (Helper `_split_at_layer_marker`, `_iter_chapters`, `_find_chapter`)
- **ADR:** `docs/architecture-decisions.md` (Eintrag 2026-05-09)
- **Konzeptdokument:** `docs/archive/memory-reform-2026-05-09.md`
- **E2E-Validierung:** `tests/e2e/scenarios/03-memory-reform.md`
