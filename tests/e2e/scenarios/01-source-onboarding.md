# Szenario 01 — Source-Onboarding

**Ziel:** Disco erkennt ein frisches Test-Projekt, registriert die
Quellen, erkennt das Duplikat (11 ↔ 01), schlaegt die PDF-Pipeline aktiv
vor.

**Voraussetzung:** Pool-Slots 01–14 sind vorhanden (synthetisch + manuell)
plus Context 06. Setup laeuft mit:

```bash
scripts/setup_e2e_project.sh e2e-smoke-01 --archive-existing
```

Vor dem Start: Dev-Server (Port 8766) laeuft, Browser zeigt das frische
Projekt `e2e-smoke-01`, Chat ist leer.

## Drehbuch

### Schritt 1 — Begruessung

User-Prompt:

> Hallo, das ist ein neues Test-Projekt. Magst Du Dich kurz orientieren
> und mir sagen, was Du hier vorfindest?

**Erwartet (Disco-Verhalten):**
- Liest `README.md`, `NOTES.md`, `.disco/memory.md`
- Liest `context/_manifest.md`
- Macht **kein** automatisches `sources_register` (das soll erst auf
  expliziten Wunsch laufen — `project-onboarding`-Skill)
- Antwortet mit: Projektname, kurzer Bestand-Hinweis (sources/ und
  context/ vorhanden, noch nicht registriert), Vorschlag fuer naechste
  Schritte

**DB-Stand bleibt unveraendert:**
- `agent_sources`: 0 Eintraege
- `agent_source_scans`: 0 Eintraege

### Schritt 2 — Sources registrieren

User-Prompt:

> Ja, leg mal los. Was haben wir denn fuer Dateien?

**Erwartet:**
- Disco ruft `sources_register` mit `scope='both'` (Default)
- Im Anschluss `sources_detect_duplicates`
- Antwort enthaelt:
  - Anzahl aktive Dateien: **15** (14 sources + 1 context)
  - Delta: 15 neu, 0 geaendert, 0 geloescht, 0 unveraendert
  - **Duplikat-Hinweis** fuer 01 ↔ 11 (gleicher SHA-256)
  - PDF-Pipeline-Vorschlag (Pflicht laut sources-onboarding-Skill)

**DB-Stand:**
- `agent_sources` (datastore): 15 Eintraege, `status='active'`,
  davon 14 mit `kind='source'`, 1 mit `kind='context'`
- `agent_source_scans`: 1 Eintrag mit `n_new=15`
- `agent_source_relations`: mind. 1 `duplicate-of`-Relation
  (kanonisch = 01_datenblatt.pdf, kopie = 11_duplikat_von_01.pdf —
  oder umgekehrt, je nachdem was zuerst registriert wurde)
- `agent_pdf_inventory`: 7 Eintraege (01, 02, 03, 08, 09, 14a, 14b —
  DWG, JPG, Excel, DOCX, PPTX landen NICHT im PDF-Inventar)

### Schritt 3 — Begleit-Metadaten

User-Prompt:

> Ich habe noch eine Excel-Datei (lieferindex), die enthaelt
> Geraete-Infos. Magst Du die als Begleit-Info zu den Dokumenten
> hinzufuegen?

**Hinweis:** `05_lieferindex.xlsx` ist im Pool, liegt aber in
`sources/` (nicht in `_meta/`). Der Skill `sources-onboarding`
erwartet sie eigentlich in `_meta/` — Disco soll erkennen, dass das
funktioniert, sobald die `key_column` passt.

**Erwartet:**
- Disco oeffnet die Excel mit `xlsx_inspect`, prueft die Spalten
- Erkennt eine `rel_path`- oder `Dateiname`-aehnliche Spalte
- Macht erst **Trockenlauf** (`commit=false`), zeigt Treffer-Quote
- Fragt vor `commit=true` nach Bestaetigung

### Schritt 4 — Sanity-Check

User-Prompt:

> Wieviele Dokumente hast Du jetzt insgesamt registriert? Davon wie
> viele PDFs?

**Erwartet:**
- Disco fragt `agent_sources` und `agent_pdf_inventory` ab
- Antwort: **15 aktive Dateien** (14 sources + 1 context),
  **7 PDFs** im Pipeline-Inventar (01, 02, 03, 08, 09, 14a, 14b)

## Pass-Kriterien

Alle muessen erfuellt sein:

- [ ] Schritt 1: Disco macht **kein** automatisches Register, sondern
      orientiert sich nur und schlaegt Naechstes vor.
- [ ] Schritt 2: `agent_sources`-Count = 15 (`status='active'`).
- [ ] Schritt 2: Duplikat 01 ↔ 11 wurde erkannt und ist als
      `duplicate-of`-Relation gespeichert.
- [ ] Schritt 2: `agent_pdf_inventory` hat 7 Eintraege (kein JPG, keine
      DWG, kein Excel, kein DOCX, kein PPTX).
- [ ] Schritt 2: Disco hat die PDF-Pipeline aktiv vorgeschlagen
      (Formulierung im sources-onboarding-Skill, „Routing → Extraktion").
- [ ] Schritt 3: Disco macht Trockenlauf vor Commit.
- [ ] Schritt 4: Antwort entspricht dem DB-Stand und nennt **7 PDFs**
      (nicht 15, nicht 14).

## Failure-Modes

**A — Disco macht direkt nach Schritt 1 ein automatisches Register:**
deutet auf zu aggressiven Skill-Trigger hin oder fehlerhaften System-
Prompt-Pfad.

**B — Duplikat-Erkennung ueberspringt:** moeglich, wenn
`sources_detect_duplicates` nicht im Skill-Workflow aktiv ist; pruefen
ob Skill-Datei `sources-onboarding.md` Step "Duplikate erkennen" als
Anschluss-Schritt enthaelt.

**C — Vorschlag fuer PDF-Pipeline fehlt:** Pflicht laut
`sources-onboarding`-Skill. Wenn fehlt → System-Prompt-Anpassung noetig.

**D — Begleit-Excel laesst sich nicht zuordnen:** Pruefen, ob
`xlsx_inspect` und Spalten-Heuristik (`rel_path`, `Dateiname`,
`Pfad`, `Datei`) greifen. Bei Mismatch → Excel ggf. anpassen.

**E — PDF-Inventory enthaelt zu viele/zu wenige Eintraege:** PDFs sind
01, 02, 03, 08, 09, 14a, 14b. JPG (04), Excel (05), DWG (07, 10),
DOCX (12), PPTX (13) duerfen NICHT im PDF-Inventar landen. Wenn doch
→ Filterlogik in `sources_register` pruefen.

## Was als naechstes folgt

Wenn Schritt 4 sauber durchlaeuft, geht's mit Szenario 02 (Context-
Onboarding) weiter — dort sichtet Disco die DCC-Excel und importiert
sie als `context_dcc_codes`-Tabelle.
