# Architektur-Entscheidungen — Disco

Dieses Dokument hält bewusste Architektur-Entscheidungen fest, die nicht
direkt aus dem Code ablesbar sind. Wenn ein Beobachter später fragt
„warum macht Disco das so / warum ist X **nicht** drin?", findet er hier
die Begründung.

Format pro Eintrag: kurzer Titel, Datum, Status (aktiv / überholt),
Kontext, Entscheidung, Konsequenzen.

---

## 2026-05-06 — docling als PDF-Engine entfernt

**Status:** aktiv

### Kontext

Disco hatte drei PDF-Engines:
- `pdf-azure-di` (Cloud, Default für Standard-PDFs)
- `pdf-azure-di-hr` (Cloud, für Pläne/Großbilder, höher aufgelöst)
- `pdf-docling-standard` (lokal, DocLayNet + TableFormer + EasyOCR auf MPS)

In der Praxis (rea-denox, lager-halle, campus-reuter) wurde
`pdf-docling-standard` über 30+ Tage **0× von Routing oder User
gewählt**. Default-Routing (`disco/docs/routing.py`) ging seit dem
Bench-Entscheid 2026-04-25 sowieso immer auf `pdf-azure-di`, weil
docling auf ~4 % der Text-PDFs halluzinierte.

Gleichzeitig zog docling **schwere Kosten** mit:
- `docling>=2.90.0`-Dependency (mit transitiven HF/torch-Paketen)
- `~/.cache/huggingface/`-Setup-Anforderung beim ersten Lauf
- `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` / `HF_DATASETS_OFFLINE`-
  Flags in `config.py` + `flows/service.py` als Defence-in-Depth
- Setup-Fallstrick „frische Maschine ohne Cache → docling kann nicht
  laden" — Backlog-Eintrag H10
- ~120 SLOC docling-spezifischer Code in `disco/pdf/markdown.py`

### Entscheidung

docling komplett aus dem Codebase entfernen. PDF-Pipeline reduziert
auf zwei Azure-DI-Engines.

### Was raus ist

- `docling>=2.90.0` aus `pyproject.toml`
- `_extract_docling_standard()` aus `src/disco/pdf/markdown.py`
- `pdf-docling-standard` aus `ENGINES_BY_KIND` (`disco/docs/__init__.py`)
- `_LEGACY_ENGINE_MAP` Eintrag in `disco/docs/pdf.py`
- HF-Offline-Flags + `_apply_offline_env`-Helper in `disco/config.py`
- `child_env.setdefault("HF_HUB_OFFLINE", ...)` etc. in
  `disco/flows/service.py`
- docling-Erwähnungen in `system_prompt.md` + Flow-READMEs

### Was bleibt

- Bestandsdaten in `agent_doc_markdown` mit `engine='docling-standard'`
  bleiben unverändert (read-only history). Schema-Spalte `engine` ist
  TEXT, kein CHECK-Constraint, also bleiben alte Werte gültig
  abrufbar; nur neue Routing-Decisions können den Wert nicht mehr
  setzen.
- `disco/pdf/`-Modul bleibt — beherbergt jetzt nur noch die
  Azure-DI-Engines.

### Wann zurück?

Falls Disco später eine vollständig **lokale PDF-Pipeline** braucht
(Offline-Anwendung, Datenschutz-Anforderung, Cloud-Cost-Cap), kann
docling über `git log -- src/disco/pdf/markdown.py` zurückgeholt
werden. Empfohlen wäre dann eine Mess-Session mit echten Dokumenten,
um die 4 %-Halluzinations-Rate gegen das aktuelle Modell-Niveau neu
zu bewerten — die Bench-Entscheidung 2026-04-25 ist von einem
älteren docling-Modellstand.

### Konsequenzen

- Disco kann **nur noch über die Cloud** PDFs extrahieren. Bei
  Foundry-Outage oder Sweden-Central-Quota-Limit gibt es keinen
  Fallback.
- Setup ist deutlich einfacher: keine 800 MB+ HF-Modell-Downloads
  beim ersten Lauf, keine MPS-/Apple-Silicon-spezifischen
  Dependencies.
- BACKLOG-Eintrag H10 (Setup-Fallstrick mit HF-Cache) wird obsolet.
