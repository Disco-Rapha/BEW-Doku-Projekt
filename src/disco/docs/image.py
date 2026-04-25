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


def extract(path: Path, engine: str) -> tuple[str, dict[str, Any]]:
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
    deployment = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5.1")

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

    # 5) Token + cost (best effort — gpt-5.1-vision-Preise nicht hardcoded,
    #    weil Foundry-Pricing variabel ist; wir rechnen 0.0 EUR und
    #    dokumentieren prompt+completion-tokens fuer spaetere Kosten-
    #    Aufrechnung)
    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

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
        # Kosten lassen wir bei 0 — die echten Foundry-Tokens stehen in meta_json
        "estimated_cost_eur": 0.0,
        "extractor_version": (
            f"{EXTRACTION_PIPELINE_VERSION}:{engine}:{engine_version}"
        ),
        "meta_json": {
            "orig_width": orig_size[0],
            "orig_height": orig_size[1],
            "resized_width": img_resized.size[0],
            "resized_height": img_resized.size[1],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
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
