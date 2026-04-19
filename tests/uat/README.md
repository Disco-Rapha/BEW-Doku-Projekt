# UAT Gold-Standards — Disco

**Was ist das hier?**

Reproduzierbare End-to-End-Testszenarien, die Disco selbststaendig durchlaufen
koennen muss, um als "produktionsreif" zu gelten. Jedes Szenario ist als
**abstraktes Verfahren** geschrieben: nicht gebunden an konkrete Dokumente,
Projekte oder Kunden, sondern an die Schritte und Akzeptanzkriterien.

**Zweck:**

1. **Regressions-Sicherung.** Wenn wir am Portal-Prompt, an Skills oder am
   Flow-Framework etwas aendern, muessen diese Szenarien weiterhin von
   Disco selbst bewaeltigt werden.
2. **Messlatte fuer Verbesserungen.** Ein Szenario mit Akzeptanzkriterien
   ist objektiver als "Disco wird besser".
3. **Spaeter automatisierbar.** Die Akzeptanzkriterien sind so formuliert,
   dass sie per SQL-Query oder `fs_list` maschinell geprueft werden koennen.
   Langfristig soll ein Test-Runner das Szenario gegen Disco spielen und
   pass/fail melden.

**Wichtig — Verfahren vs. konkrete Daten:**

Die Dokumente, Kataloge und Projekt-Namen in den Szenarien sind **Beispiele**,
nicht die Testdaten selbst. Die realen Testfixtures liegen im Workspace
(`~/Disco/projects/<test-projekt>/`) und koennen wechseln — das Szenario bleibt
stabil, solange die *Art* der Daten passt (z.B. "eine Sammlung technischer PDFs
und ein Klassifikations-Katalog").

## Struktur eines Szenarios

```
tests/uat/<name>/
├── scenario.md      — narratives Test-Drehbuch (User-Sicht, was Disco tut)
├── acceptance.md    — messbare Akzeptanzkriterien pro Phase
└── fixture-spec.md  — wie eine passende Test-Fixture aussehen muss
```

## Aktuelle Szenarien

| Slug | Titel | Stand |
|---|---|---|
| `doku-klassifikation` | Dokumente klassifizieren nach Kunden-Schema | Gold-Standard v1 (2026-04-18) |

## Wie man ein Szenario durchspielt (manuell)

1. Test-Projekt im Workspace anlegen, das der `fixture-spec.md` entspricht.
2. Chat mit Disco im Projekt starten.
3. Nacheinander die User-Messages aus `scenario.md` (Abschnitt "Ablauf") an
   Disco senden — **ohne Zwischen-Nudges**.
4. Nach jeder Phase die `acceptance.md`-Kriterien der Phase pruefen.
5. Abweichungen protokollieren (idealerweise in `~/Disco/uat-bug-log.md`).

## Wie man ein Szenario weiterentwickelt

- **Bug gefunden?** Erst in `~/Disco/uat-bug-log.md` dokumentieren, dann fixen.
  Nach Fix: erneut durchspielen und bestaetigen.
- **Neues Kriterium?** In `acceptance.md` ergaenzen, Versions-Datum unten
  hochzaehlen.
- **Verfahren geaendert?** In `scenario.md` aktualisieren und Versions-Datum
  hochzaehlen. Nicht die Historie loeschen — ergaenzen.
