# Network-Egress-Policy

**Status:** verbindlich. Gilt fuer Dev und Prod. Aenderungen brauchen
explizite User-Genehmigung im Chat plus Eintrag in dieses Dokument.

Disco arbeitet **lokal-first**: Kundendaten verlassen den Rechner nicht,
ausser ueber eine **abschliessend aufgelistete Menge** von genehmigten
externen Verbindungen. Diese Liste ist hart — neue Verbindungen werden
nicht ungeplant hinzugefuegt, weder im Code noch in den UI-Bibliotheken
noch in den Engines.

## Genehmigte Egress-Endpoints

| Endpoint | Zweck | Daten | Geo | Genehmigt |
|---|---|---|---|---|
| `*.services.ai.azure.com/api/projects/Sweden-central-deployment` | Foundry Project (GPT-5.1 Agent + Vision) | Prompts, Tool-Outputs, Bilder fuer Image-Extraction | EU/Sweden Central | seit Phase 1 |
| Azure Document Intelligence (Sweden Central) | PDF-Layout-OCR (Engines `pdf-azure-di`, `pdf-azure-di-hr`) | PDF-Bytes | EU/Sweden Central | seit Phase 1 |
| `api.github.com` | nur fuer User-getriebenes `gh pr create` etc. — niemals automatisch | Code-Diffs, PR-Bodies | global | manuell, explizit |

**Keine weiteren Egress-Verbindungen.** Wenn ein neuer Use-Case eine
externe Abhaengigkeit braucht (Cloud-Service, NPM-Registry, CDN, Tracker,
Telemetrie), wird sie **vor** der Implementierung im Chat begruendet,
genehmigt und dann in dieser Tabelle ergaenzt.

## Was bewusst LOKAL bleibt

Diese Sachen wurden in der Vergangenheit als externe Abhaengigkeiten
diskutiert und sind bewusst lokal eingerichtet:

| Komponente | Frueher als Cloud-Variante diskutiert | Heute |
|---|---|---|
| `dxf-viewer` JS-Library | esm.sh CDN | gebundlet unter `src/disco/api/static/lib/dxf-viewer.bundle.mjs`, ueber `/static/lib/...` ausgeliefert |
| `marked.js`, `pdf.js`, SheetJS, PapaParse, DOMPurify, highlight.js | CDN (cdn.jsdelivr.net etc.) | aktuell teils ueber CDN — **TODO**: in einer Folge-Iteration ebenfalls lokal bundeln |
| Docling-Modelle (DocLayNet, TableFormer, EasyOCR) | Hugging Face Hub | Modelle werden beim ersten Lauf gecached; danach offline |
| **DWG-Konverter** | (alt) closed-source ODA File Converter | **libredwg** (GNU/GPL-3, OSS) — lokal gebaut via `scripts/install-libredwg.sh`, installiert in `~/.local/libredwg/`, kein Netzwerk im Betrieb |
| ezdxf, openpyxl, PyMuPDF, pypdf, Pillow | – | Python-Pakete im venv, kein Netzwerk |

## Prod-spezifische Verschaerfung

Prod laeuft auf `~/Disco/` mit `disco-prod-agent` (Foundry). Die
Genehmigungs-Tabelle gilt dort **strikt** — keine Ausnahmen, auch nicht
"nur kurz fuer einen Test". Wenn eine neue Verbindung gebraucht wird:

1. **Erst auf Dev** umsetzen, mit User-Diskussion.
2. **Tabelle hier** erweitern.
3. **Dann** ueber den ueblichen ff-only-Deploy nach Prod.

## CDN-Bibliotheken — heute noch offen

Im Web-UI laeuft heute teilweise noch CDN-Code (markdown-it, pdf.js,
SheetJS, PapaParse, DOMPurify, highlight.js — alle ueber
`cdn.jsdelivr.net` o.ae.). Das war **Stand vor 2026-04-25** so eingerichtet
und wurde bewusst hingenommen, weil:

- Reine Code-Downloads, kein Daten-Upload.
- Browser-Caching macht den Effekt nach dem ersten Aufruf neutral.

**Geplante Aenderung:** alle Web-UI-Libs analog zum dxf-viewer lokal
bundeln (Folge-Sprint). Dann faellt auch dieser Egress weg.

## Verifizieren

Schneller Sanity-Check, was rausgeht:

```bash
# Watch egress-Verbindungen (macOS)
sudo lsof -nP -i -p $(pgrep -f 'uvicorn.*disco') 2>/dev/null
```

Im Browser-Devtools (Network-Tab): keine Hosts ausser `127.0.0.1:8765`/
`8766` und die in der Tabelle oben gelisteten Azure-Endpoints duerften
auftauchen. Wenn doch: das ist ein Bug, **bitte sofort melden** und nicht
"erst mal so lassen".

## Revisions-Log

| Datum | Aenderung | Genehmigt durch |
|---|---|---|
| 2026-04-25 | Initiale Fassung. dxf-viewer lokal gebundlet (vorher esm.sh). | User-Anweisung im Chat |
| 2026-04-25 | DWG-Konverter ODA File Converter (closed) → libredwg (GPL-3, OSS), lokal in `~/.local/libredwg/`. Keine neue Egress-Verbindung. | User-Anweisung im Chat |
