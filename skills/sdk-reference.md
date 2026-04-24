---
name: sdk-reference
description: Verlaessliche SDK-Signaturen fuer Azure Document Intelligence, Azure OpenAI (Structured Output) und die feste 3-Engine-PDF-Pipeline (docling-standard / azure-di / azure-di-hr) via `src/disco/pdf/markdown.py`. Nachschlagewerk, wenn Du einen DI-/LLM-/Engine-Call schreibst — bevor Du irgendetwas "aus dem Kopf" tippst.
when_to_use: "Azure Document Intelligence", "DI", "prebuilt-layout", "ocrHighResolution", "OCR", "Azure OpenAI", "GPT-5 API", "Structured Output", "response_format", "json_schema", "AzureKeyCredential", "Docling", "docling-standard", "DocumentConverter", "PdfPipelineOptions", "TableFormerMode", "extract_markdown", "pdf_to_markdown", IMMER wenn Du einen Flow mit externem Azure-Call ODER Aufruf des Engine-Dispatchers baust.
---

# Skill: sdk-reference

Du hast **kein Internet** und die Azure-SDKs aendern sich staendig.
Deine Trainingsdaten sind fuer diese Signaturen **nicht verlaesslich**.
Wenn Du einen DI- oder LLM-Call baust: **erst hier nachschlagen, dann
schreiben**. Nicht improvisieren.

## Regel — niemals halluzinieren

1. **Keine `disco.services.*`-Imports erfinden.** So ein Modul gibt es
   nicht. Nimm direkt das offizielle Azure-SDK.
2. **Keine Parameter raten.** `content=data`, `file_bytes=...`,
   `document=...` — gibt es alles nicht. Die korrekten Parameter
   stehen unten, zeichengenau.
3. **Kein `try/except ImportError`-Fallback mit weichen Fehlern.**
   Wenn das SDK fehlt → harter `RuntimeError`, der Flow bricht ab
   und das Problem ist sofort sichtbar (statt 20 Items spaeter).

---

## Azure Document Intelligence

### Paket + Imports

```python
# pyproject.toml hat bereits: azure-ai-documentintelligence
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
```

### Credentials aus Settings (nicht os.getenv)

```python
from disco.config import settings

endpoint = settings.azure_doc_intel_endpoint
key = settings.azure_doc_intel_key
if not endpoint or not key:
    raise RuntimeError(
        "AZURE_DOC_INTEL_ENDPOINT/KEY fehlen in settings / .env"
    )

client = DocumentIntelligenceClient(
    endpoint=endpoint,
    credential=AzureKeyCredential(key),
)
```

Hinweis: Im Flow-Subprocess laedt `runner_host` das `.env` automatisch,
daher funktionieren sowohl `settings.azure_doc_intel_endpoint` als auch
`os.getenv("AZURE_DOC_INTEL_ENDPOINT")`. Praefer `settings` fuer
typisierte Werte und bessere Fehlermeldungen.

### PDF → Markdown mit OCR-HighRes

```python
with open(pdf_path, "rb") as f:
    data = f.read()

poller = client.begin_analyze_document(
    model_id="prebuilt-layout",
    body=data,                       # bytes ODER file-like ODER {"urlSource": "..."}
    content_type="application/pdf",  # Pflicht bei bytes/stream
    features=["ocrHighResolution"],  # Optional-Liste; leer = Standard-OCR
    output_content_format="markdown",  # wichtig — sonst plain-text
)
result = poller.result()
```

**Parameter-Wahrheit:**

| Parameter | Typ | Wert |
|---|---|---|
| `model_id` | str | `"prebuilt-layout"` (Struktur+OCR) ODER `"prebuilt-read"` (nur OCR) |
| `body` | bytes / IO / AnalyzeDocumentRequest | **nicht** `content=`, **nicht** `document=` |
| `content_type` | str | `"application/pdf"`, `"image/png"`, `"image/jpeg"` |
| `features` | list[str] \| None | `["ocrHighResolution"]`, `["languages"]`, `["keyValuePairs"]`, ... |
| `output_content_format` | str | `"markdown"` oder `"text"` (default `"text"`) |

**NICHT EXISTIERENDE Methoden (nicht erfinden):**
- `begin_analyze_document_from_stream(...)` — gibt es nicht.
- `analyze_pdf(...)` — gibt es nicht.
- `extract_markdown(...)` — gibt es nicht.

### Ergebnis auswerten

```python
# result ist ein AnalyzeResult. Das Markdown steht direkt in .content:
markdown_text: str = result.content

# Seitenzahl:
pages_count: int = len(result.pages) if result.pages else 0

# Optional: Tabellen, Key-Value-Pairs etc. — nur wenn Du sie wirklich brauchst:
# for table in (result.tables or []): ...
# for kv in (result.key_value_pairs or []): ...
```

`result.content` ist immer gesetzt, wenn der Poller durchgelaufen ist.
Kein Grund fuer `hasattr(result, 'content')`-Abfragen.

### Kosten-Orientierung (fuer Budget-Limit)

| Modell | Modus | Preis (Sweden Central, 2026-04-24) |
|---|---|---|
| `prebuilt-layout` | Standard | 0,00868 EUR/Seite (8,68 EUR / 1000) |
| `prebuilt-layout` | HighRes (`ocrHighResolution`) | 0,01389 EUR/Seite (13,89 EUR / 1000) |
| `prebuilt-read` | Standard | ~0,0015 EUR/Seite |

Layout-Preise aus Azure-Rechnung verifiziert (2026-04-24). Fuer neue
Regionen/Modelle Azure-Pricing pruefen statt aus dem Kopf zitieren.

---

## Azure OpenAI — Chat Completions mit Structured Output

### Paket + Imports

```python
# pyproject.toml hat bereits: openai
from openai import AzureOpenAI
```

### Client aus Settings

```python
from disco.config import settings

client = AzureOpenAI(
    azure_endpoint=settings.azure_openai_endpoint,   # z.B. https://<res>.openai.azure.com
    api_key=settings.azure_openai_key,
    api_version=settings.azure_openai_api_version,   # GA: "2024-10-21"
)
```

**WICHTIG — api-version NICHT hardcoden und NICHT raten:**
- **Gueltige** GA-Versionen (stand 2026): `"2024-10-21"`, `"2024-06-01"`, `"2024-02-01"`.
- **Gueltige** Preview-Versionen: `"2024-10-01-preview"`, `"2024-08-01-preview"`.
- Der String `"2024-10-21-preview"` (GA-Datum + `-preview`) **existiert NICHT** und
  fuehrt zu `HTTP 404 Resource not found`. Gleiches gilt fuer beliebige
  Fantasie-Kombinationen.
- `"preview"` ohne Datum funktioniert **nur** fuer Foundry `/openai/v1` und
  die Responses-API, **nicht** fuer klassische `chat/completions` Calls.
- Immer `settings.azure_openai_api_version` lesen statt String im Code — die `.env`
  ist die Single-Source-of-Truth. (UAT-Bug #6 + Folgebug api-version).

Fuer `response_format=json_schema` mit `strict: True` braucht es mindestens
`2024-08-01-preview` oder `2024-10-21` (GA). Defaults in `.env` sind darauf
abgestimmt — einfach `settings.azure_openai_api_version` nutzen.

### Endpoint-URL — Foundry vs. Azure-OpenAI-Resource

Dieselbe Azure-Resource kommt unter **zwei Hostnamen** — je nachdem, welches
SDK man nutzt:

| SDK | Hostname | Beispiel |
|---|---|---|
| `openai.AzureOpenAI` (Chat Completions) | `<name>.openai.azure.com` | `https://myorg-foundry.openai.azure.com` |
| `azure-ai-projects` / Foundry Portal-Agent | `<name>.services.ai.azure.com/api/projects/<proj>` | `https://myorg-foundry.services.ai.azure.com/api/projects/MyOrg-Project` |

Fuer Flow-Worker mit `openai.AzureOpenAI` **immer** die `.openai.azure.com`-Variante
nehmen (`settings.azure_openai_endpoint` in `.env`). Mit der `services.ai.azure.com/api/projects/...`-URL
scheitert das Client-Init mit
`httpx.UnsupportedProtocol: Request URL is missing an 'http://'`.

### Strukturierter JSON-Output mit json_schema

Fuer Klassifikations-Flows **IMMER** `response_format=json_schema` —
dann entfaellt eigenes JSON-Parsing und Halluzinations-Cleanup.

```python
import json

schema = {
    "name": "dcc_klassifikation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "gewerk": {
                "type": "string",
                "enum": [
                    "0 - Allgemein", "1 - Verfahrenstechnik",
                    "2 - Maschinentechnik", "3 - Elektrotechnik",
                    "4 - Leittechnik", "5 - Bautechnik",
                    "6 - Rohrleitungstechnik",
                ],
            },
            "master_dcc": {"type": "string"},
            "dcc_bezeichnung_master": {"type": "string"},
            "dcc_alternativ": {"type": "string"},
            "conf_score_master": {"type": "number", "minimum": 0, "maximum": 1},
            "ist_zusammenstellung": {"type": "string", "enum": ["Ja", "Nein"]},
            "agentenkommentar": {"type": "string"},
        },
        "required": [
            "gewerk", "master_dcc", "dcc_bezeichnung_master",
            "dcc_alternativ", "conf_score_master",
            "ist_zusammenstellung", "agentenkommentar",
        ],
    },
}

response = client.chat.completions.create(
    model=settings.azure_openai_deployment,  # z.B. "gpt-5"
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ],
    response_format={"type": "json_schema", "json_schema": schema},
)

payload = json.loads(response.choices[0].message.content)
# payload ist jetzt garantiert schema-konform (strict=True)
```

**Wichtig:**
- `strict: True` → OpenAI garantiert schema-konformes JSON.
- `additionalProperties: False` + `required` → **alle** Properties muessen
  aufgelistet sein, sonst Validation-Error beim Erstellen.
- Enums sind Dein Freund — lieber eine Enum-Liste als `"type": "string"`
  mit Freitext, sonst klassifiziert das Modell "kreativ".
- **Kein `temperature=0.1` oder aehnliches bei gpt-5!** Das Modell akzeptiert
  nur die Default-Temperature (1) und lehnt andere Werte mit
  `HTTP 400 "Unsupported value: 'temperature' does not support 0.1 with this
  model. Only the default (1) value is supported."` ab. Determinismus kommt
  bei gpt-5 ueber `response_format=json_schema strict=True` und klare
  Prompt-Anweisungen, nicht mehr ueber Temperature. Also: **`temperature`
  einfach weglassen** — Default ist 1.

### Kosten-Tracking — PFLICHT bei jedem LLM-Call

**Ohne `run.add_cost(...)` bleibt `total_cost_eur` = 0 und das UI zeigt
falsche Budgets an.** Deshalb gibt es seit 2026-04-19 einen Einzeiler:

```python
# EMPFOHLEN — das SDK macht usage-Extraktion + Pricing + Budget-Check:
tokens_in, tokens_out, eur = run.add_cost_from_azure_response(response)

# Falls Du die Tokens fuer Deine eigene Ergebnis-Tabelle brauchst, hast Du
# sie jetzt als Tuple zurueck. In den Run fliessen sie automatisch.
```

Der Helper:
- liest `response.usage.prompt_tokens` / `.completion_tokens` (Chat Completions) ODER
  `.input_tokens` / `.output_tokens` (Responses-API)
- berechnet EUR via `compute_cost_eur(model, tokens_in, tokens_out)` aus
  `MODEL_PRICING_USD_PER_MTOK` in `disco.flows.sdk`
- nimmt als Modell `response.model` (oder den `model=`-Parameter, wenn gesetzt)
- ruft intern `run.add_cost(eur, tokens_in, tokens_out)` → Budget-Pause greift

Fallback, falls Du mit einem fremden API arbeitest, das dieses Format
nicht erfuellt:

```python
usage = response.usage
tokens_in = usage.prompt_tokens
tokens_out = usage.completion_tokens
run.add_cost(eur=<selbst_berechnet>, tokens_in=tokens_in, tokens_out=tokens_out)
```

**Merksatz:** *Jeder `client.chat.completions.create(...)`-Aufruf muss
innerhalb desselben `try`-Blocks von einer `run.add_cost_from_azure_response(...)`-
Zeile begleitet werden. Kein Ausnahmefall.*

### Markdown-Input trimmen (Context-Budget)

GPT-5 schluckt grosse Kontexte, aber jeder Token kostet Geld. Fuer
Dokument-Klassifikation: **erste ~50k + letzte ~20k Zeichen** reichen
meist — Titel- und Revisions-Bloecke sind am Anfang/Ende.

```python
def trim_markdown(md: str, head: int = 50_000, tail: int = 20_000) -> str:
    if len(md) <= head + tail:
        return md
    return md[:head] + "\n\n[... TRIMMED ...]\n\n" + md[-tail:]
```

---

## Ergebnisse in die Projekt-DB schreiben

Jeder Flow schreibt typischerweise pro Item eine Zeile in eine
`agent_*`-Tabelle. Falle **nicht** in das alte Muster mit handgestricktem
`INSERT INTO ... VALUES (?, ?, ?, ...)`: Ein Komma zu wenig, Spaltenreihen-
folge nicht 1:1 → `17 values for 18 columns` (UAT-Bug #6 Ursprung).

### EMPFOHLEN — `run.db.insert_row(table, dict)`

```python
run.db.insert_row(
    "agent_dcc_results",
    {
        "source_id": source_id,
        "rel_path": rel_path,
        "Gewerk": payload["Gewerk"],
        "Master DCC": payload["Master DCC"],
        "DCC Bezeichnung (Master)": payload["DCC Bezeichnung (Master)"],
        "DCC (Alternativ)": payload["DCC (Alternativ)"],
        "Conf.score DCC (Master)": payload["Conf.score DCC (Master)"],
        "Ist Zusammenstellung": payload["Ist Zusammenstellung"],
        "Agentenkommentar": payload["Agentenkommentar"],
        "model": settings.azure_openai_deployment,
        "prompt_version": "DCC Klassifikation Prompt.md",
        "run_id": run.run_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_eur": eur,
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    on_conflict="update:source_id",  # Upsert
)
```

Vorteile:
- **Spaltennamen sind lesbar** — kein Abzaehlen mehr, welches `?` welche
  Spalte meint.
- **Schema-Validierung:** Tippfehler in Spaltennamen (`"masterdcc"` statt
  `"Master DCC"`) werfen `ValueError` sofort, nicht erst nach 493 Items.
- **Upsert-Muster als Einzeiler:** `on_conflict="update:source_id"` erzeugt
  das `ON CONFLICT(source_id) DO UPDATE SET ...` fuer alle uebrigen Keys.
- **Sonderzeichen in Spalten** (Leerzeichen, Umlaute, Punkte) werden automatisch
  mit `"..."` gequotet.

`on_conflict`-Varianten:

| Wert | Verhalten |
|---|---|
| `None` (Default) | Plain INSERT, Conflict → Exception |
| `"replace"` | `INSERT OR REPLACE` (loescht + neu einfuegen) |
| `"ignore"` | `INSERT OR IGNORE` (Duplikat still verwerfen) |
| `"update:col1[,col2,...]"` | Upsert via `ON CONFLICT(...)` |

### Wann Du handgeschriebenes SQL trotzdem brauchst

Bei komplexen Queries (`CTE`, Joins in UPDATE, `RETURNING`, mehrere
Tabellen) bleibt `run.db.execute("UPDATE ...", (...))`. `insert_row`
ist gezielt fuer das haeufigste Muster: *„ich habe ein Ergebnis-dict
und will es in eine Tabelle schreiben"*.

---

## PDF-Extraktion — die feste Pipeline

**Fuer neue Flows gilt:** PDFs werden NICHT mehr ad hoc konvertiert.
Jedes Dokument durchlaeuft einmal die Pipeline
`pdf_routing_decision` → `pdf_to_markdown`; das Ergebnis liegt in
`agent_pdf_markdown` (Tabelle per Migration 008). Disco liest nur
noch ueber `pdf_markdown_read`.

Der Engine-Dispatcher lebt in `src/disco/pdf/markdown.py` und kennt
drei Engines:

| Engine | Ziel-Seitentyp | Kosten |
|---|---|---|
| `docling-standard` | Text + Tabellen, evtl. Scans (DocLayNet + TableFormer ACCURATE + EasyOCR, MPS) | 0 EUR |
| `azure-di` | A4-Scans, wenig Text | 0,00868 EUR/Seite (8,68 EUR/1000) |
| `azure-di-hr` | vector-drawing, Plan-Format, grosse Bilder (ocrHighResolution) | 0,01389 EUR/Seite (13,89 EUR/1000) |

Braucht ein Flow ad hoc Markdown (etwa fuer einen Einzeltest), ruft
er `extract_markdown(abs_path, engine)` aus `disco.pdf` auf — das
liefert `(md, meta)` mit `n_pages / char_count / duration_ms /
estimated_cost_eur`. Kein Direkt-Kontakt zu Docling oder DI mehr,
die komplette Engine-Logik ist im Dispatcher gekapselt.

### Offline-Modus (Hintergrund)

Disco laeuft vollstaendig offline fuer ML-Modelle. `src/disco/config.py`
setzt beim Start `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
`HF_DATASETS_OFFLINE=1`. Flags werden an Subprozesse (Flow-Runner,
`run_python`) vererbt. Docling laedt NUR aus
`~/.cache/huggingface/hub/` — wenn ein Modell fehlt, wirft der Run
`OfflineModeIsEnabled` statt still zu downloaden.

Der Engine-Dispatcher kuemmert sich um die Docling-Optionen
(DocLayNet + TableFormer ACCURATE + EasyOCR, `scale=2.0`, MPS mit
`num_threads=4`). Nutzer aendert hier nichts.

### Azure Document Intelligence — WICHTIG fuer Flow-Autoren

Wenn Du einen Flow bastelst, der selbst DI aufruft (ausserhalb der
Markdown-Pipeline), gilt:

- Import aus `azure.ai.documentintelligence`, nicht aus
  `disco.services.*`.
- `begin_analyze_document` bekommt `body=<bytes>`, nicht `content=`
  oder `document=` oder `file=`.
- `content_type="application/pdf"` ist Pflicht wenn `body` bytes ist.
- Fuer vector-drawing / Plaene: `features=["ocrHighResolution"]` —
  sonst fehlen KKS-Labels im Zeichnungskopf.
- Output-Format `markdown`: `prebuilt-layout` mit `output_content_format=DocumentContentFormat.MARKDOWN`.
- Credentials aus `settings.*`, nicht `os.getenv` raw.

---

## Pruef-Checkliste, bevor Du den Flow startest

- [ ] Imports sind aus `azure.ai.documentintelligence` bzw. `openai`,
      **nicht** aus `disco.services.*`.
- [ ] `begin_analyze_document` kriegt `body=<bytes>`, nicht `content=` /
      `document=` / `file=`.
- [ ] `content_type="application/pdf"` ist gesetzt, wenn `body` bytes ist.
- [ ] `response_format={"type": "json_schema", ...}` bei LLM-Klassifikation.
- [ ] Credentials kommen aus `settings.*`, nicht raw `os.getenv` (letzteres
      funktioniert nur, weil der Runner-Host `.env` laedt — `settings`
      ist ausdrucksstaerker).
- [ ] Fehlerpfad wirft `RuntimeError`, kein weicher `try/except`-Fallback.
- [ ] **Nach jedem LLM-Call `run.add_cost_from_azure_response(response)`** —
      sonst zeigt das UI `0 EUR` (UAT-Bug #10).
- [ ] **Fuer INSERTs in agent_*-Tabellen `run.db.insert_row(table, dict)`** —
      keine handgezaehlten Tupel mehr (UAT-Bug #6 Ursprung).
