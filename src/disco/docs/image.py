"""Bild-Extractor — GPT-5.1 Vision (Foundry / Sweden Central).

Engine:
  - image-gpt5-vision : Foundry GPT-5.1 multimodal, ein Standard-Prompt
                        liefert Beschreibung + OCR-Text + Strukturierte Erkennung

Output-Format:
  ## Beschreibung
  <2-4 Saetze>

  ## Erkannter Text
  <jeder Block, eine Zeile pro Block>

  ## Strukturierte Erkennung
  - **KKS / Tags**: ...
  - **Hersteller / Modell**: ...
  - **Technische Werte**: ...
  - **Sonstiges**: ...

Bild-Vorbereitung:
  - Lange Seite max. 2048 px (Resize per Pillow, Aspect-Ratio bleibt)
  - JPEG-Encoding fuer base64 (Quality 85)
  - PNG-Originale werden in JPEG konvertiert (Token-Budget)
"""
from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path
from typing import Any

from . import EXTRACTION_PIPELINE_VERSION

logger = logging.getLogger(__name__)

_ENGINE_VERSIONS: dict[str, str] = {
    "image-gpt5-vision": "1.0",
}

_MAX_LONG_EDGE_PX = 2048
_JPEG_QUALITY = 85

_SYSTEM_PROMPT = """Du bist ein präziser Bild-Extraktor für technische
Dokumentation. Du bekommst ein Bild und gibst es als strukturiertes
Markdown zurück. Halte Dich exakt an das vorgegebene Format. Erfinde
nichts — wenn ein Wert nicht erkennbar ist, lass ihn weg oder schreibe
"nicht erkennbar"."""

_USER_PROMPT = """Analysiere dieses Bild und gib **genau** das folgende
Markdown-Format zurück (keine zusätzlichen Sektionen, keine Einleitung):

## Beschreibung
2-4 Sätze: Was zeigt das Bild? Kontext, auffällige Elemente. Kurz und
faktisch, keine Spekulationen.

## Erkannter Text
Jeder erkennbare Text-Block, eine Zeile pro Block. Reihenfolge nach
Sichtbarkeit (groß/oben → klein/unten). Bei mehrsprachigen Texten:
beide Sprachen mit aufnehmen. Wenn nichts lesbar: "_(kein lesbarer Text)_"

## Strukturierte Erkennung
- **KKS / Tags**: gefundene Codes wie +X1, =B01, NHEW02 (KKS-Beschriftungen)
- **Hersteller / Modell**: wenn auf Schild oder Schrift erkennbar
- **Technische Werte**: Spannung, Leistung, Type, Seriennummer, Maße
- **Sonstiges**: was zur Klassifikation/Suche dienen könnte

Wenn eine Zeile keine Werte hat: weglassen, nicht "—" oder "nicht
vorhanden" schreiben."""


DEFAULT_FLOW_MODEL = "gpt-5.1"
"""Hardcoded Default-Modell fuer Image-Extraction-Flow.

Bewusst NICHT aus FOUNDRY_MODEL_DEPLOYMENT-ENV gelesen — die ENV ist
fuer den Disco-Agent (Chat) reserviert (heute gpt-5.4-prod). Flows
sollen einen eigenen, kostenoptimierten Default haben (gpt-5.1 ist
~30% guenstiger als gpt-5.4 bei Image-typischen Output-Mengen).

Override pro Run via Flow-Config: `{"model": "gpt-5.4-prod"}` →
`dispatch_extract(model_deployment=...)` → hier als Parameter.
"""


def extract(
    path: Path,
    engine: str,
    *,
    model_deployment: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Extrahiert Bild-Inhalt nach strukturiertem Markdown.

    model_deployment:
      - None (Default): nutzt DEFAULT_FLOW_MODEL = "gpt-5.1" (hardcoded).
      - gesetzt: wird direkt fuer den Vision-Call genutzt (per-Run-Override
        aus Flow-Config, z.B. "gpt-5.4-prod" fuer hoechste Qualitaet oder
        "gpt-5.1-mini" fuer Kosten-Optimierung).

    Der genutzte Deployment-Name landet im meta_json, sodass das Cost-
    Tracking weiss, mit welchem Modell der Output erzeugt wurde.
    """
    if engine not in _ENGINE_VERSIONS:
        raise ValueError(f"Unbekannte Image-Engine: {engine!r}")

    # 1) Bild laden + ggf. resizen
    from PIL import Image
    img = Image.open(path)
    orig_size = img.size  # (width, height)
    img_resized = _maybe_resize(img, _MAX_LONG_EDGE_PX)

    # 2) JPEG-encode + base64
    buf = io.BytesIO()
    rgb = img_resized.convert("RGB")
    rgb.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    img_bytes = buf.getvalue()
    b64 = base64.b64encode(img_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    # 3) Foundry/Azure-OpenAI-Client (gleiche Auth wie agent/core.py)
    client = _build_openai_client()
    # Default-Modell fuer Flow-Engine ist hardcoded, NICHT aus ENV. Damit
    # haben Disco-Agent (Chat, gpt-5.4-prod) und Flows (gpt-5.1) saubere
    # Trennung der Modell-Defaults.
    deployment = model_deployment or DEFAULT_FLOW_MODEL

    # 4) Vision-Call via chat.completions
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                ],
            },
        ],
        temperature=0.0,
    )

    md = resp.choices[0].message.content or ""
    md = md.strip() + "\n"

    # 5) Token-Usage + Cost-Berechnung via disco.pricing
    from disco.pricing import extract_token_usage, get_foundry_price

    usage = extract_token_usage(getattr(resp, "usage", None))
    price = get_foundry_price(deployment)
    if price is not None:
        cost_eur = price.cost_eur(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            cached_prompt_tokens=usage["cached_tokens"],
        )
    else:
        # Unbekanntes Deployment — Tokens trotzdem mitschreiben, Kosten 0
        # damit die Pipeline nicht crasht. Im Log ein Hinweis.
        logger.warning(
            "Kein Foundry-Pricing fuer deployment=%s — estimated_cost_eur=0",
            deployment,
        )
        cost_eur = 0.0

    char_count = len(md)
    engine_version = _ENGINE_VERSIONS.get(engine, "1.0")

    meta: dict[str, Any] = {
        "file_kind": "image",
        "engine": engine,
        "n_units": 1,
        "char_count": char_count,
        "unit_offsets": [
            {
                "unit_num": 1,
                "unit_label": "image",
                "char_start": 0,
                "char_end": char_count,
            }
        ],
        "estimated_cost_eur": cost_eur,
        "extractor_version": (
            f"{EXTRACTION_PIPELINE_VERSION}:{engine}:{engine_version}"
        ),
        "meta_json": {
            "orig_width": orig_size[0],
            "orig_height": orig_size[1],
            "resized_width": img_resized.size[0],
            "resized_height": img_resized.size[1],
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "cached_tokens": usage["cached_tokens"],
            "deployment": deployment,
        },
    }
    return md, meta


def _maybe_resize(img: "Image.Image", max_long_edge: int) -> "Image.Image":
    """Resize so dass long_edge <= max_long_edge (Aspect-Ratio bleibt)."""
    w, h = img.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return img
    scale = max_long_edge / long_edge
    new_w = int(w * scale)
    new_h = int(h * scale)
    from PIL import Image as _Image
    return img.resize((new_w, new_h), _Image.LANCZOS)


def _build_openai_client():
    """Foundry / Azure-OpenAI-Client analog zu disco.agent.core.

    Deutlich schlanker — Image-Extraktion braucht keine Tools/Agents,
    nur ein chat.completions-Call.
    """
    from openai import OpenAI, AzureOpenAI

    foundry_endpoint = os.environ.get("FOUNDRY_ENDPOINT")
    foundry_key = os.environ.get("FOUNDRY_API_KEY")
    az_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    az_key = os.environ.get("AZURE_OPENAI_KEY")
    az_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

    if foundry_endpoint and foundry_key:
        base_url = foundry_endpoint.rstrip("/") + "/openai/v1"
        return OpenAI(base_url=base_url, api_key=foundry_key)
    if az_endpoint and az_key:
        return AzureOpenAI(
            azure_endpoint=az_endpoint, api_key=az_key, api_version=az_api_version
        )
    raise RuntimeError(
        "Kein Foundry-/Azure-OpenAI-Auth fuer Image-Extraktion. "
        "FOUNDRY_ENDPOINT + FOUNDRY_API_KEY in .env setzen."
    )


__all__ = ["extract"]
