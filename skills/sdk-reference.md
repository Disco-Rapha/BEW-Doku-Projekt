---
name: sdk-reference
description: Verlaessliche SDK-Signaturen fuer Azure Document Intelligence, Azure OpenAI (Structured Output) und die LOKALE Docling-VLM-Pipeline (Granite-Docling-MLX, SmolDocling-MLX, Standard). Nachschlagewerk, wenn Du einen DI-/LLM-/Docling-Call schreibst — bevor Du irgendetwas "aus dem Kopf" tippst.
when_to_use: "Azure Document Intelligence", "DI", "prebuilt-layout", "OCR", "Azure OpenAI", "GPT-5 API", "Structured Output", "response_format", "json_schema", "AzureKeyCredential", "Docling", "Granite-Docling", "SmolDocling", "MLX", "VlmPipeline", "VlmPipelineOptions", "DocumentConverter", "PdfPipelineOptions", "TableFormerMode", "lokale Markdown-Konvertierung", IMMER wenn Du einen Flow mit externem Azure-Call ODER lokaler Docling-Pipeline baust.
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

| Modell | Modus | Preis grob |
|---|---|---|
| `prebuilt-layout` | Standard | ~0,010 EUR/Seite |
| `prebuilt-layout` | HighRes | ~0,015 EUR/Seite |
| `prebuilt-read` | Standard | ~0,0015 EUR/Seite |

Genaue Preise: Azure-Pricing pruefen, nicht aus dem Kopf zitieren.

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

## Docling — Lokale PDF-Konvertierung (Granite-MLX / SmolDocling-MLX / Standard)

**Wann lokal statt DI?** Wenn Budget knapp ist oder Compliance keine
Cloud erlaubt. Auf M1/M2/M3 Macs kommt Granite-Docling-MLX in der
Markdown-Qualitaet erstaunlich nah an DI heran — kostenlos, dafuer
langsamer (~10-30s/Seite vs. 1-3s bei DI Cloud).

Du hast in Disco das Tool `markdown_extract` (siehe Skill
`markdown-extractor` fuer Engine-Wahl). Wenn Du in einem **Flow**
direkt gegen Docling gehst, brauchst Du die Imports + Signaturen
unten — sie sind hier abgedruckt, weil Disco kein Internet hat und
auf die Doku auf docling.io nicht zugreifen kann.

### Paket + Voraussetzungen

```python
# pyproject.toml hat bereits:
#   docling[vlm]>=2.90.0
#
# Das [vlm]-Extra zieht auf macOS-arm64 automatisch:
#   - mlx>=0.21.0
#   - mlx-vlm>=0.4.3
#   - peft, qwen-vl-utils, sentencepiece
#
# Auf anderen Plattformen kommt 'transformers' statt mlx-vlm —
# Granite-Docling-Transformers hat aber KEIN MPS-Support, also
# fuer M1 IMMER die _MLX-Variante nehmen.
```

### Offline-Modus — WICHTIG vor dem ersten Aufruf

Disco laeuft per Default **vollstaendig offline** fuer ML-Modelle.
`src/bew/config.py::_apply_offline_env` setzt beim Start:

```
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_DATASETS_OFFLINE=1
```

Diese Flags werden an Subprozesse (Flow-Runner, `run_python`) vererbt.
Docling/transformers/HF-Hub machen dann **keinen Online-Check**, sondern
laden ausschliesslich aus `~/.cache/huggingface/hub/`.

**Was das fuer Dich als Flow-Autor heisst:**

1. **Niemals im Runner HF-Flags umbiegen.** Kein
   `os.environ["HF_HUB_OFFLINE"] = "0"` in runner.py, kein
   `huggingface_hub.login()`, kein `snapshot_download(...)`.
   Der Runner verlaesst sich darauf, dass das Modell im Cache liegt.

2. **Vor dem Run einmalig:** Nutzer fuehrt
   `uv run python scripts/download_models.py` aus — das ist die
   einzige legitime Stelle, an der Disco online geht. Das Skript
   deaktiviert die Flags lokal fuer den einen Prozess.

3. **Symptom „Runner haengt minutenlang ohne GPU-Last"**: Modell nicht
   im Cache, `HF_HUB_OFFLINE=1` fehlt → Docling macht Online-HEAD-Check
   gegen `huggingface.co` und wartet auf Socket-Timeout.
   Fix: `uv run python scripts/download_models.py` und Run neu starten.

4. **Defence-in-Depth:** `src/bew/flows/service.py` setzt die Flags
   nochmal explizit auf dem Subprocess-Env, falls das Parent-`os.environ`
   sie nicht mehr hat. Du musst im Runner NICHTS zusaetzlich tun.

### Engine 1: Granite-Docling-MLX (DEFAULT auf M1)

Beste Markdown-Qualitaet auf Apple Silicon, speziell fuer Docling-
Konvertierung trainiert (IBM 2025).

```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import VlmPipelineOptions
from docling.datamodel.vlm_model_specs import GRANITEDOCLING_MLX
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

pipeline_options = VlmPipelineOptions(vlm_options=GRANITEDOCLING_MLX)

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=VlmPipeline,             # Pflicht — VLM braucht eigene Pipeline-Klasse!
            pipeline_options=pipeline_options,
        )
    }
)

result = converter.convert(str(pdf_path))         # akzeptiert str, nicht Path
markdown_text: str = result.document.export_to_markdown()
n_pages: int = len(result.pages) if result.pages else 0
```

**`GRANITEDOCLING_MLX`-Spec (zum Nachschlagen, NICHT zum Aendern):**

```python
GRANITEDOCLING_MLX = InlineVlmOptions(
    repo_id="ibm-granite/granite-docling-258M-mlx",
    prompt="Convert this page to docling.",
    response_format=ResponseFormat.DOCTAGS,
    inference_framework=InferenceFramework.MLX,
    supported_devices=[AcceleratorDevice.MPS],   # NUR Apple Silicon!
    scale=2.0,
    temperature=0.0,
    max_new_tokens=8192,
    stop_strings=["</doctag>", "<|end_of_text|>"],
)
```

**Was passiert beim ersten Aufruf:**
- HuggingFace-Download von `ibm-granite/granite-docling-258M-mlx`
  (~500MB), gecached unter `~/.cache/huggingface/hub/models--ibm-granite--granite-docling-258M-mlx/`
- Folgeruns nutzen den Cache — kein Internet noetig

### Engine 2: SmolDocling-MLX (Schneller, kleiner)

Der kleinere Bruder — gut fuer simple Layouts, ~2x schneller als Granite.

```python
from docling.datamodel.vlm_model_specs import SMOLDOCLING_MLX

pipeline_options = VlmPipelineOptions(vlm_options=SMOLDOCLING_MLX)
# Rest wie bei Granite — gleiche VlmPipeline + DocumentConverter
```

`SMOLDOCLING_MLX` Spec:
```python
SMOLDOCLING_MLX = InlineVlmOptions(
    repo_id="docling-project/SmolDocling-256M-preview-mlx-bf16",
    prompt="Convert this page to docling.",
    response_format=ResponseFormat.DOCTAGS,
    inference_framework=InferenceFramework.MLX,
    supported_devices=[AcceleratorDevice.MPS],
    scale=2.0,
    temperature=0.0,
    stop_strings=["</doctag>", "<end_of_utterance>"],
)
```

### Engine 3: Standard-Pipeline (DocLayNet + TableFormer + EasyOCR)

Klassische Docling-Pipeline, schnellste lokale Variante. Funktioniert
auch auf Nicht-Apple-Hardware.

```python
from docling.datamodel.accelerator_options import (
    AcceleratorDevice,
    AcceleratorOptions,
)
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

opts = PdfPipelineOptions()
opts.do_ocr = True                                # OCR fuer Scan-PDFs
opts.do_table_structure = True                    # Tabellen-Erkennung
opts.table_structure_options.mode = TableFormerMode.ACCURATE   # statt FAST
opts.table_structure_options.do_cell_matching = True
opts.images_scale = 2.0                           # 2x DPI -> bessere OCR
opts.accelerator_options = AcceleratorOptions(
    num_threads=4,
    device=AcceleratorDevice.MPS,                 # auf M1 die Apple-GPU nutzen
)

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=opts)
        # KEIN pipeline_cls hier — Default ist Standard-PdfPipeline
    }
)

result = converter.convert(str(pdf_path))
markdown_text = result.document.export_to_markdown()
```

**`TableFormerMode` Werte:**

| Wert | Verhalten |
|---|---|
| `TableFormerMode.FAST` | ~3x schneller, schlechter bei verschachtelten Tabellen |
| `TableFormerMode.ACCURATE` | Default fuer ernsthafte Markdown-Pipelines |

**`AcceleratorDevice` Werte:**

| Wert | Plattform |
|---|---|
| `AcceleratorDevice.MPS` | Apple Silicon (M1/M2/M3) |
| `AcceleratorDevice.CUDA` | NVIDIA-GPU |
| `AcceleratorDevice.CPU` | Fallback, sehr langsam |
| `AcceleratorDevice.AUTO` | Docling waehlt selbst — meist MPS auf Mac |

### Page-Range fuer Mini-Tests

```python
# Statt durchgaengig — nur Seiten 1-3 (1-indexiert, inklusive Grenzen)
result = converter.convert(str(pdf_path), page_range=(1, 3))
```

Funktioniert sowohl bei VlmPipeline als auch bei der Standard-
Pipeline. Fuer Engine-Vergleich mit grossen Plaenen unverzichtbar
(sonst dauert es bei einem 80-Seiten-Plan + Granite-MLX 30 Minuten).

### Was Du aus `result` lesen kannst

```python
result = converter.convert(str(pdf_path))

# Markdown-String (das wirst Du fast immer wollen):
md = result.document.export_to_markdown()

# Anderer Export-Format:
text = result.document.export_to_text()           # nur Text, kein Markdown
html = result.document.export_to_html()           # vollstaendiges HTML
docling_dict = result.document.export_to_dict()   # interne DocTags-Repraesentation

# Seitenzahl (zwei Wege, je nach Engine):
n_pages = len(result.pages) if result.pages else 0
# Fallback bei VLM-Pipelines:
if not n_pages and hasattr(result.document, 'pages'):
    n_pages = len(result.document.pages)

# Pro-Seite-Iteration (selten gebraucht):
for page in result.document.pages:
    # page hat layout, tables, text-Blocks etc.
    ...

# Tabellen separat (wenn Du sie ausserhalb des Markdowns brauchst):
for table in result.document.tables or []:
    ...
```

### Disco-Convention: Header voranstellen

Wenn Du in einem Flow Markdown schreibst, halte Dich an dieselbe Header-
Konvention wie Disco's `markdown_extract` und `extract_pdf_to_markdown`:

```python
from datetime import datetime, timezone

header = (
    f"<!-- Extrahiert aus: {rel_path} -->\n"
    f"<!-- Engine: granite-mlx (Granite-Docling-258M (MLX, Apple Silicon)) -->\n"
    f"<!-- Modell: ibm-granite/granite-docling-258M-mlx | "
    f"Device: MPS (MLX) | Seiten: {n_pages} | "
    f"{len(md)} Zeichen | Dauer: {duration:.1f}s -->\n"
    f"<!-- Extrahiert am: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} -->\n\n"
)
target.write_text(header + md, encoding="utf-8")
```

### Time-Logging im Flow (PFLICHT bei lokalen Engines)

Lokale VLM-Pipelines koennen Cold-Start (erstes Modell-Laden) ~30-60s
brauchen, dann pro Seite ~10-30s. Loggen, sonst weisst Du beim
Debug nicht ob die Engine haengt oder normal arbeitet.

```python
import time

t_start = time.monotonic()
result = converter.convert(str(pdf_path))
duration = time.monotonic() - t_start

run.log(f"granite-mlx: {pdf_path.name} ({n_pages}p) -> "
        f"{duration:.1f}s ({duration / max(n_pages, 1):.1f}s/page)")
```

### Throughput-Schaetzung (M1 32GB, gemessen 2026-04)

| Engine | s/Seite | Seiten/h | 1k Docs (a 4 S.) in |
|---|---|---|---|
| `GRANITEDOCLING_MLX` | 15-25 | ~150-240 | ~17-27h |
| `SMOLDOCLING_MLX` | 7-12 | ~300-510 | ~8-13h |
| Standard (TableFormer ACCURATE, MPS) | 4-8 | ~450-900 | ~4-9h |
| Standard (TableFormer FAST, MPS) | 2-5 | ~720-1800 | ~2-6h |

Fuer eigene Vermessung: Benchmark-Flow `markdown-engine-benchmark`
(siehe Skill `markdown-extractor`).

### Caches + Disk-Footprint

| Cache | Pfad | Groesse |
|---|---|---|
| HuggingFace-Modelle (VLM) | `~/.cache/huggingface/hub/` | ~500MB pro VLM-Modell |
| Docling-Standard-Modelle | `~/.cache/docling/` | ~200MB (DocLayNet + TableFormer) |
| EasyOCR-Modelle | `~/.cache/EasyOCR/` | ~70MB pro Sprache |

Disco laeuft per Default **vollstaendig offline** (siehe Offline-Modus
weiter oben). Die Modelle liegen im Cache, Docling zieht sie sofort
lokal. Ein neuer Mac braucht genau einmal
`uv run python scripts/download_models.py` — das ist die einzige
Stelle, an der Disco online geht. Im normalen Betrieb wird NICHTS
„beim ersten Aufruf" geladen; wenn ein Modell fehlt, knallt der
Run mit `OfflineModeIsEnabled` statt heimlich zu downloaden.

### Fallstricke + Anti-Patterns

**1. `pipeline_cls=VlmPipeline` VERGESSEN bei VLM-Engines**

```python
# FALSCH — laeuft die Standard-Pipeline und ignoriert die VlmPipelineOptions:
PdfFormatOption(pipeline_options=VlmPipelineOptions(vlm_options=GRANITEDOCLING_MLX))

# RICHTIG:
PdfFormatOption(
    pipeline_cls=VlmPipeline,                     # <- DAS ist der Schluessel
    pipeline_options=VlmPipelineOptions(vlm_options=GRANITEDOCLING_MLX),
)
```

**2. `GRANITEDOCLING_TRANSFORMERS` auf M1 erwischt**

Es gibt zwei Granite-Specs:
- `GRANITEDOCLING_MLX` → MLX, **MPS supported**, M1-fertig.
- `GRANITEDOCLING_TRANSFORMERS` → transformers, **KEIN MPS** (nur CPU/CUDA/XPU)!
  Das laeuft auf M1 nur ueber CPU und ist ~10x langsamer als die MLX-Variante.

Auf Apple Silicon **immer** die `_MLX`-Variante.

**3. `Path` statt `str` an `converter.convert(...)`**

```python
# FALSCH — wirft TypeError bei aelteren docling-Versionen:
result = converter.convert(pdf_path)              # pdf_path ist Path

# RICHTIG:
result = converter.convert(str(pdf_path))
```

**4. EasyOCR-Sprache nicht gesetzt**

```python
# Default = englisch. Fuer deutsche Dokumente:
opts.ocr_options = EasyOcrOptions(lang=["de", "en"])
```

Importiert von `docling.datamodel.pipeline_options.EasyOcrOptions`.
Bei rein deutschen technischen Dokumenten reduziert das die OCR-
Halluzinationen merklich.

**5. `do_ocr=True` bei reinen Text-PDFs (Verschwendung)**

OCR braucht Zeit. Wenn die PDF rein textbasiert ist, lieber
`pdf_extract_text` (pypdf) — Faktor 100 schneller.

**6. Memory-OOM bei sehr grossen PDFs (Granite-MLX)**

Granite-Docling-MLX laedt Seiten als Bilder (Scale 2.0). Bei einem
80-Seiten-Plan mit hochaufgeloesten Plantitelblocks geht 32GB RAM
moeglicherweise schwimmen. Workaround: `page_range` fuer Tranche-
Verarbeitung, oder auf Standard-Pipeline ausweichen.

### Pruef-Checkliste fuer einen Docling-Flow

- [ ] `docling[vlm]` ist in `pyproject.toml` (nicht nur `docling`).
- [ ] Bei VLM-Engine: `pipeline_cls=VlmPipeline` ist gesetzt.
- [ ] Auf Mac: `GRANITEDOCLING_MLX` (nicht `_TRANSFORMERS`).
- [ ] `converter.convert(str(pdf_path))` — String, nicht Path.
- [ ] Time-Logging vorhanden (`time.monotonic()` vor + nach `convert`).
- [ ] Mini-Test mit `page_range=(1, 3)` vor dem Bulk-Lauf.
- [ ] `result.document.export_to_markdown()` — nicht `.export_to_text()`.
- [ ] Header mit Quelle + Engine + Dauer voranstellen (Disco-Konvention).
- [ ] Fuer Bulk: kein direkter `markdown_extract`-Tool-Aufruf, sondern
      Flow (siehe Skill `flow-builder`).

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
