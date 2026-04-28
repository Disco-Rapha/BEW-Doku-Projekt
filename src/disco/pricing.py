"""Zentrale Foundry-/Azure-Pricing-Konstanten in EUR.

EINE Source-of-Truth fuer alle Cost-Berechnungen — Image-Engine, Flow-LLM-
Calls, Chat-Cost-Tracking. Alle anderen Module rufen `get_foundry_price()`
oder `compute_cost_eur()` und bekommen identische Werte.

Werte sind die **echten Sweden Central Data Zone Standard-Listpreise in
EUR pro 1M Tokens** (das Tier in dem unsere Foundry-Resource liegt).
Microsoft publiziert das direkt in EUR — keine USD→EUR-Umrechnung noetig.

WICHTIG — Werte regelmaessig pruefen:
  - https://azure.microsoft.com/de-de/pricing/details/ai-foundry/
  - Region "Sweden Central" + Tier "Data Zone Standard"
  - Stand 2026-04-27 (BEW): bei Aenderung Datum hochziehen.

Cached-Input-Discount:
  Foundry/Azure-OpenAI cacht den System-Prompt-Praefix ueber Calls
  hinweg (typisch >50% des Inputs). Bei gpt-5.1: ~50% Rabatt vom
  Input-Preis. Bei gpt-5.4: 90% Rabatt (also nur 10% des Input-Preises).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenPrice:
    """Preise pro 1 Million Tokens, in EUR.

    Wir lesen Werte direkt aus der Azure-Pricing-Seite (Sweden Central
    Data Zone Standard, EUR-Listpreise) und speichern sie unverarbeitet.
    """
    input_eur_per_1m: float
    cached_input_eur_per_1m: float
    output_eur_per_1m: float

    def cost_eur(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_prompt_tokens: int = 0,
    ) -> float:
        """EUR-Kosten fuer einen Call.

        cached_prompt_tokens ist ein TEILBETRAG von prompt_tokens. Wir
        rechnen den nicht-gecachten Rest mit input_eur und den gecachten
        Anteil mit cached_input_eur.
        """
        regular_prompt = max(0, prompt_tokens - cached_prompt_tokens)
        cost = (
            regular_prompt * self.input_eur_per_1m
            + cached_prompt_tokens * self.cached_input_eur_per_1m
            + completion_tokens * self.output_eur_per_1m
        ) / 1_000_000
        return round(cost, 6)


# ---------------------------------------------------------------------------
# Foundry GPT-Familie — Sweden Central Data Zone Standard EUR-Listpreise
# ---------------------------------------------------------------------------
#
# Quelle: Azure-Pricing-Seite. Microsoft publiziert in EUR direkt fuer
# Sweden Central Data Zone Standard. Bei unbekanntem Cached-Anteil:
# vom Globalen-USD-Listpreis-Rabatt-Verhaeltnis abgeleitet.
#
# Drift-Hinweis: globale USD-Listpreise sind hoeher (z.B. gpt-5.1 Input
# $2.50 = €2.30 mit 0.92er-Kurs vs. €1.20 hier). Sweden-Central ist im
# Data-Zone-Tarif spuerbar guenstiger — Microsoft hat dafuer einen eigenen
# Preisplan.

FOUNDRY_PRICING: dict[str, TokenPrice] = {
    # gpt-5.1: Sweden Central Data Zone Standard, Stand 2026-04-22
    # (Azure-Pricing-Seite Screenshot, in flows/sdk.py-History dokumentiert).
    # Cached-Input ist auf der Azure-Seite oft nicht separat gelistet —
    # wir nehmen 50% vom Input-Preis (entspricht globalem 50%-Rabatt).
    "gpt-5.1": TokenPrice(
        input_eur_per_1m=1.20,
        cached_input_eur_per_1m=0.60,   # 50% Rabatt (Schaetzung)
        output_eur_per_1m=9.55,
    ),

    # gpt-5.4: Sweden Central Data Zone Standard hochgerechnet.
    # - Input ist global $2.50 (gleich wie gpt-5.1) → in SC-DZ vermutlich
    #   ebenfalls €1.20.
    # - Output ist global $15.00 (50% teurer als gpt-5.1) → SC-DZ skaliert
    #   mit gleichem Faktor 9.55/10.00 → €14.32.
    # - Cached-Input ist global 90% Rabatt → €0.12.
    # Bei Verifikation der echten SC-DZ-EUR-Werte fuer gpt-5.4 hier anpassen.
    "gpt-5.4": TokenPrice(
        input_eur_per_1m=1.20,
        cached_input_eur_per_1m=0.12,   # 90% Rabatt (gpt-5.4-spezifisch)
        output_eur_per_1m=14.32,
    ),

    # gpt-5 / gpt-4o: noch keine SC-DZ-EUR-Verifikation. Konservative
    # Annahme = gpt-5.1-Werte. Wenn jemand diese Modelle aktiv nutzt:
    # Werte aus Pricing-Seite verifizieren.
    "gpt-5":  TokenPrice(input_eur_per_1m=1.20, cached_input_eur_per_1m=0.60, output_eur_per_1m=9.55),
    "gpt-4o": TokenPrice(input_eur_per_1m=1.20, cached_input_eur_per_1m=0.60, output_eur_per_1m=9.55),
}


def get_foundry_price(deployment: str) -> TokenPrice | None:
    """TokenPrice fuer ein Foundry-Deployment, oder None wenn unbekannt.

    Heuristik: prefix-match (z.B. 'gpt-5.1-mini' fallback auf 'gpt-5.1',
    'gpt-5.4-prod' auf 'gpt-5.4').
    """
    if deployment in FOUNDRY_PRICING:
        return FOUNDRY_PRICING[deployment]
    # Laengster passender Prefix gewinnt (damit 'gpt-5.4' nicht auf 'gpt-5'
    # fallback faellt). Sortierung: laengste Keys zuerst.
    for known in sorted(FOUNDRY_PRICING.keys(), key=len, reverse=True):
        if deployment.startswith(known):
            return FOUNDRY_PRICING[known]
    return None


def compute_cost_eur(
    deployment: str,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cached_prompt_tokens: int = 0,
) -> float:
    """Convenience-Wrapper: Cost-EUR fuer einen Foundry-Call.

    Wird von Flow-Engines und vom Chat-Cost-Tracking genutzt. Wenn das
    Deployment nicht in FOUNDRY_PRICING ist, wird 0.0 zurueckgegeben (mit
    None ist Cost-Aggregation tricky).
    """
    price = get_foundry_price(deployment)
    if price is None:
        return 0.0
    return price.cost_eur(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_prompt_tokens=cached_prompt_tokens,
    )


def extract_token_usage(usage: Any) -> dict[str, int]:
    """Liest Token-Counts aus einer OpenAI-SDK-Usage-Antwort.

    Robust gegen ungesetzte Felder (manche Foundry-Calls liefern keine
    cached_tokens, dann ist der Wert 0).
    """
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = int(getattr(details, "cached_tokens", 0) or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
    }


__all__ = [
    "TokenPrice",
    "FOUNDRY_PRICING",
    "get_foundry_price",
    "compute_cost_eur",
    "extract_token_usage",
]
