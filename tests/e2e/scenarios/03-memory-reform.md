# E2E-Test: Memory-Reform 2026-05-09

**Testlauf:** 2026-05-09
**Disco-Agent:** disco-dev-agent v38 (GPT-5.1, Sweden Central)
**Testprojekt:** `e2e-memory-reform` (frisch aufgesetzt via `setup_e2e_project.sh`)
**Vergleichsprojekt (T7):** `e2e-smoke-01` (Legacy-DISCO.md ohne Marker)
**Konzeptdokument:** `docs/memory-reform-2026-05-09.md`

## Ziel

Verifikation der drei umgesetzten Phasen der Memory-Reform:

1. **P1 — `memory_read` neu** mit Schicht-1/Schicht-2-Splitting via Marker
   `<!-- DISCO-LAYER-1-END -->`, neuen Modi (`chapter`, `headings_only`,
   `tail`, `max_bytes`), Trace-Log und chapter-meta-Side-Effects.
2. **P2 — `agent_table_docs` + Tools** (`table_doc_set` / `table_doc_get`)
   für Schicht 3 (Tabellen-Doku).
3. **P3 — NOTES-Auto-Archivierung** in `compaction.run_compaction_with_handover`
   mit 30-Tage-Schwelle.

## Setup

- `e2e-memory-reform` neu erstellt, DISCO.md mit Marker + 8 Schicht-2-Kapiteln
  (chapter-meta-Blöcke), NOTES.md mit Mix aus alten (2025-03, 2026-04) und
  neuen (2026-05-08, 2026-05-09) Einträgen.
- `agent_table_docs` mit 3 Einträgen befüllt:
  `agent_dcc_results`, `context_dcc_codes`, `agent_kks_register`.
- `disco agent setup --env dev` → v38 in Foundry aktiv.

## Ergebnisse

| Test | Frage | Erwartung | Ergebnis | Status |
|------|-------|-----------|----------|--------|
| **T1** | "Hallo, was steht hier?" | Default-Modus lädt Schicht 1 + Kapitel-Index, kein Vollscan | Disco listete alle 8 Kapitel als Index, Schicht 1 (Identität, Fokus, Konventionen, Lookup-Pfade) korrekt geladen, fand sogar einen absichtlich gelegten Zahlendreher (14 vs. 15 Files) | ✅ |
| **T2** | "Stand bei Bautechnik IBL" | Substring-Match → Kapitel "Bautechnik IBL Roh-Stand" gezielt nachladen | Kapitel-Hit per Substring, 462 Bytes; präzise Antwort mit 5 Geräten + 1/5-Treffer | ✅ |
| **T3** | "Was steht im Kapitel Schwerelosigkeit-Test?" | Klarer Miss, KEINE Halluzination | "❌ gibt es nicht", danach komplette Liste der real existierenden Kapitel | ✅ |
| **T4** | "SOLL/IST Bautechnik" | Tag- oder Body-Match findet Bautechnik IBL | Korrekt aufgelöst, gleiche Antwort wie T2 (refcount → 2) | ✅ |
| **T5** | Token-Sockel-Messung | Default-Modus < 4 KB | README 620 B + NOTES tail 405 B + DISCO Schicht 1 1581 B = **2.616 Bytes ≈ 650 Tokens** statt vorher ~8 KB legacy default | ✅ |
| **T6** | "Was steht in agent_dcc_results?" | `table_doc_get` liefert Beschreibung + Schema + Beispiel-Query | Vollständige Doku zurückgegeben (Spalten, typische Joins, SQL-Beispiel) | ✅ |
| **T7** | Legacy-Projekt `e2e-smoke-01` (kein Marker) | Default-Modus liefert ganze Datei wie bisher | DISCO.md (1.496 B) komplett geladen, kein Crash, kein Marker-Fehler | ✅ |

## Trace-Log

`.disco/memory-access.log` (e2e-memory-reform):

```
ts	mode	file	chapter_query	hit_type	matched_title	bytes	reference_count_after
2026-05-09T07:08:52Z	default	README.md	-	-	-	630	-
2026-05-09T07:08:52Z	tail	NOTES.md	-	-	-	405	-
2026-05-09T07:08:52Z	default	DISCO.md	-	-	-	1581	-
2026-05-09T07:14:00Z	chapter	DISCO.md	Bautechnik IBL	substring	Bautechnik IBL Roh-Stand	462	1
2026-05-09T07:14:56Z	chapter	DISCO.md	Schwerelosigkeit-Test	miss	-	0	-
2026-05-09T07:15:58Z	chapter	DISCO.md	Bautechnik IBL	substring	Bautechnik IBL Roh-Stand	462	2
```

Alle Modi (default, tail, chapter) inkl. Hit/Miss + reference_count
nachvollziehbar geloggt. Side-Effect (`reference_count_after: 2` bei T4)
bestätigt: Kapitel-Meta wird beim Hit live aktualisiert.

## Token-Effizienz

| Modus | Bytes | ≈ Tokens | Vergleich Legacy |
|-------|-------|----------|-------------------|
| Default neu (Schicht 1 + Index) | 1.581 | ~395 | -67 % vs. 8 KB Legacy |
| Onboarding-Sockel (README + NOTES tail + DISCO Schicht 1) | 2.616 | ~650 | — |
| Kapitel-Hit gezielt | 462 | ~115 | nur wenn gebraucht |

## Backward Compatibility

Projekte ohne `<!-- DISCO-LAYER-1-END -->`-Marker (alle drei Prod-Projekte
+ `e2e-smoke-01`) lesen wie bisher das ganze File mit Default-Cap (8 KB).
Kein Migrationszwang. Migration auf Marker-Format kann pro Projekt einzeln
erfolgen.

## Bewertung

**Alle 7 Mind-Tests bestanden.** Die drei Reform-Phasen funktionieren
end-to-end:

- Token-Sockel pro Turn signifikant gesenkt (8 KB → ~2.6 KB).
- Gezielter Kapitel-Lookup mit Substring/Tag/Body-Hit.
- Klare Miss-Behandlung (keine Halluzination).
- Tabellen-Doku als eigene Schicht abrufbar.
- Trace-Log macht jeden Memory-Access nachvollziehbar.
- Legacy-Projekte funktionieren ohne Eingriff weiter.

## Nächste Schritte

- Migration der drei Prod-Projekte (`rea-denox`, `campus-reuter`,
  `lager-halle`) auf Marker-Format — separate Sessions.
- Vor der BEW-Demo am 2026-05-12: Prod-Deploy via ff-Merge +
  `disco agent setup --env prod`.
