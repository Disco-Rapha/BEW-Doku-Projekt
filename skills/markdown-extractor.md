---
name: markdown-extractor
description: Wahl der richtigen Engine fuer "PDF -> Markdown". Vier Optionen mit unterschiedlichen Trade-offs (Granite-Docling-MLX, SmolDocling-MLX, Docling-Standard, Azure DI). Wann was — und wann lieber pypdf statt aller drei.
when_to_use: "Markdown extrahieren", "PDF in Markdown", "OCR", "Granite Docling", "Docling", "lokale Konvertierung", "Document Intelligence", "extract_pdf_to_markdown", "markdown_extract", "welche Engine".
---

# Skill: markdown-extractor

Disco hat **vier** Wege, eine PDF in Markdown zu konvertieren — drei
lokal (kostenlos), einer per Azure-Cloud (gut, aber teuer). Diese
Entscheidung hat *erhebliche* Folgen: bei 2.000 Dokumenten ist der
Unterschied zwischen 0 EUR (lokal) und ~30 EUR (DI HighRes). Ebenso
zwischen 24h Laufzeit (lokal-Granite) und 1h (DI Cloud).

Diese Routine hilft Dir, die richtige Engine fuer den jeweiligen Job
zu waehlen — ohne raten oder nacheinander durchprobieren.

## Die vier Optionen

| Tool | Engine-Param | Quelle | Modell | EUR / 1k Seiten | s / Seite (M1) |
|---|---|---|---|---|---|
| `markdown_extract` | `granite-mlx` (default) | lokal (MLX) | Granite-Docling-258M | 0 | 10-30 |
| `markdown_extract` | `smol-mlx` | lokal (MLX) | SmolDocling-256M | 0 | 5-15 |
| `markdown_extract` | `standard` | lokal (PyTorch+MPS) | DocLayNet + TableFormer ACCURATE + EasyOCR | 0 | 3-8 |
| `extract_pdf_to_markdown` | — | Azure Cloud | DI prebuilt-layout (HighRes) | ~15 | 1-3 (+ Netzwerk) |

> Werte sind Erfahrungswerte M1 MacBook Pro 32GB, gemessen 2026-04.
> Eigene Vermessung mit dem Benchmark-Flow `markdown-engine-benchmark`
> empfohlen.

## Die Entscheidungs-Routine

### Frage 1 — Geht es um eine einzelne PDF aus dem Chat?

**Ja** → `markdown_extract` mit `engine='granite-mlx'`. Default-Pfad
(`<projekt>/.disco/markdown-extracts/granite-mlx/<dateiname>.md`),
fertig. Die VLM-Gewichte liegen lokal im HF-Cache (Disco laeuft offline,
`HF_HUB_OFFLINE=1`). Falls ein Modell fehlt, bricht der Aufruf mit
`OfflineModeIsEnabled` ab — dann einmalig
`uv run python scripts/download_models.py` laufen lassen.

**Nein, mehr als ~10 PDFs** → Kein Tool-Aufruf, sondern **Flow** bauen
(siehe Skill `flow-builder`). Begruendung: jeder Aufruf blockiert den
Chat-Turn. Bei 30s/Seite × 10 PDFs × 5 Seiten ist der Chat 25 Minuten
tot. Flows laufen im Subprocess, der Nutzer kann weitermachen.

### Frage 2 — Welche Engine fuer den Bulk-Lauf?

Drei Achsen:

1. **Qualitaet:** Wie wichtig sind Tabellen, Plantitelblock, gemischtes
   Layout?
2. **Tempo:** Wieviele Dokumente in welcher Zeit?
3. **Hardware:** M1/M2/M3 (MLX rockt) oder Intel-Mac (MLX faellt aus)?

**Default-Wahl auf Apple Silicon: `granite-mlx`.**
- Bessere Markdown-Struktur als `standard`, vor allem bei Tabellen
  (Spalten-/Zellen-Erkennung).
- Speziell fuer Docling-Konvertierung trainiert (IBM, 2025).
- Ist das was wir DI ablouesen wollen.

**Wann `smol-mlx`?**
- Sehr simple Layouts (reine Texte, einfache Tabellen).
- Du brauchst 2x Tempo und akzeptierst leicht schlechtere Tabellen.
- Klein genug, dass es auch auf 16GB-Macs sauber laeuft.

**Wann `standard`?**
- Auf Nicht-Apple-Hardware (MLX nicht verfuegbar).
- Schnellste lokale Variante; gut fuer simple Plaene und viele Seiten.
- Schwach bei komplexen Plantitelblocks und handschriftlichen Anteilen.

**Wann Azure DI (`extract_pdf_to_markdown`)?**
- Beste Qualitaet bei Plantitelblocks, handschriftlich annotierten
  Plaenen, sehr komplexen Tabellen.
- Du hast Budget und brauchst es schnell (1h fuer 2.000 Docs).
- Internet ist verfuegbar (Disco lokal hat normalerweise keine Internet-
  Beschraenkung — nur das Modell-Wissen ist offline).
- **Nicht** als Default — pro Bulk-Lauf vorher mit dem Nutzer
  abklaeren wegen der Kosten.

**Wann `pdf_extract_text` (pypdf, gar kein OCR)?**
- Die PDF ist textbasiert (kein Scan), Du brauchst nur den rohen Text.
- Schnellste Variante (~0.1s/Seite), praktisch kein Speicher.
- KEINE Layout-Information, keine Tabellen-Struktur, keine OCR fuer
  Scans. Nicht zur Markdown-Konvertierung geeignet.

### Frage 3 — Wie testen?

**IMMER** vor dem Bulk: Mini-Test mit 3-5 repraesentativen PDFs.
Setze `page_range=[1, 3]` falls die Doc dick ist, das laeuft in
Sekunden statt Minuten:

```
markdown_extract(
    path="sources/Beispiel-Plantitelblock.pdf",
    engine="granite-mlx",
    page_range=[1, 3]
)
```

Schau Dir das Ergebnis mit `fs_read` an. Wenn Tabellen sauber sind,
Hierarchie passt, Sonderzeichen okay → take it to bulk.

## Outputs verstehen

`markdown_extract` gibt zurueck:

```json
{
  "path": "sources/foo.pdf",
  "output_path": ".disco/markdown-extracts/granite-mlx/foo.md",
  "engine": "granite-mlx",
  "engine_label": "Granite-Docling-258M (MLX, Apple Silicon)",
  "pages": 5,
  "page_range": null,
  "markdown_chars": 12384,
  "duration_s": 87.3,
  "seconds_per_page": 17.5,
  "device": "MPS (MLX)",
  "model_repo": "ibm-granite/granite-docling-258M-mlx",
  "hint": "Markdown gespeichert unter ..."
}
```

Drei Felder sind entscheidend fuer Diagnose:
- **`seconds_per_page`** — Vergleichswert fuer Throughput-Schaetzung.
- **`markdown_chars`** — sehr klein bedeutet "Konvertierung hat fast
  nichts erkannt" (eventuell Scan-PDF, Engine-Wechsel pruefen).
- **`pages`** — wenn 0 trotz erfolgreicher Konvertierung: Modell-Bug,
  Engine wechseln.

## Speicherort + Konvention

Default-Pfad pro Engine in einem getrennten Unterordner:

```
<projekt>/.disco/markdown-extracts/
├── granite-mlx/
│   ├── PEN-Erklaerung.md
│   └── Berechnung-YOUSD10GQ511.md
├── smol-mlx/
│   └── ... (gleiche Datei, andere Engine)
└── standard/
    └── ...
```

Vorteil: derselbe Quell-PDF kann durch alle Engines geschickt werden,
ohne sich gegenseitig zu ueberschreiben — Voraussetzung fuer den
Benchmark-Flow.

`output_path` nur setzen, wenn Du eine spezielle Konvention im Projekt
brauchst (z.B. `markdowns/<source-name>.md`). Muss dann **innerhalb
des Projekts** liegen — die Sandbox blockt absolute Pfade ausserhalb.

## Throughput-Schaetzung (M1, 32GB)

Schnelle Faustregel fuer Planung:

| Engine | Seiten/Stunde | 2000 Docs (a 4 S.) in |
|---|---|---|
| `granite-mlx` | 200 | ~40h |
| `smol-mlx` | 400 | ~20h |
| `standard` | 600 | ~13h |
| Azure DI | 2000 | ~4h |

Das ist **NICHT** linear — sehr lange PDFs (Plaene) brechen den
Schnitt nach unten, kurze Datenblaetter nach oben. Eigene Vermessung
mit Benchmark-Flow ueber repraesentative Stichprobe.

## Was NICHT tun

- **Nicht** `markdown_extract` in einer Schleife aus dem Chat heraus
  ueber 100 PDFs — das blockiert den Turn und der Watcher weckt Disco
  irgendwann mit `done`-Heartbeat. Stattdessen: Flow.
- **Nicht** wahllos `engine` umschalten ohne Mini-Test (3-5 Seiten).
  Modelle haben unterschiedliche Schwaechen — was bei DI klappt,
  klappt nicht zwingend bei Granite und umgekehrt.
- **Keine** `output_path` ausserhalb des Projekts setzen — die Sandbox
  blockt das mit `output_path ausserhalb des Projekts`.
- **Nicht** sich auf `seconds_per_page` aus einem einzigen Lauf
  verlassen — bei kleinen Dokumenten ueberwiegt der Modell-Load
  (Cold-Start). Mehrere Laeufe oder den Benchmark-Flow nutzen.
- **Nicht** Granite oder Smol auf einem Intel-Mac probieren — MLX
  braucht Apple Silicon. Da landet `standard`.

## Verbindung zu anderen Skills

- **`sdk-reference`** — vollstaendige Code-Beispiele fuer Docling
  (VLM- und Standard-Pipeline) zum Aufnehmen in eigene Flow-Runner.
  Pflicht-Lektuere bevor Du einen `markdown_extract`-Flow schreibst.
- **`flow-builder`** — Routine fuer das Anlegen eines Bulk-Flows, der
  alle PDFs durch `markdown_extract` (oder Azure DI) jagt.
- **`python-executor`** — wenn Du fuer ein Mini-Skript einfach
  ad-hoc-Konvertierung brauchst (z.B. zum Test einer einzelnen Seite).
