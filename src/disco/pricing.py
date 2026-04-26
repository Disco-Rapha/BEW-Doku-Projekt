"""Zentrale Foundry-/Azure-Pricing-Konstanten + EUR-Umrechnung.

Eine einzige Stelle, die wir pflegen muessen, wenn sich Preise aendern.
Alle Engines (heute Image-Vision; spaeter Token-basierte Klassifikation,
Embeddings, etc.) lesen aus diesem Modul.

WICHTIG — Werte regelmaessig pruefen:
  - Foundry-Dashboard → Pricing oder
  - https://azure.microsoft.com/de-de/pricing/details/ai-foundry/
  - Stand: 2026-04-26 (BEW). Bei Aenderung: hier updaten + Datum hochziehen.

Cached-Input-Discount:
  Foundry/Azure-OpenAI cacht das System-Prompt-Praefix ueber Calls hinweg
  (typisch >50% des Inputs). Cached-Input kostet ~50% des regulaeren
  Input-Tokens-Preises. Bei Bulk-Vision-Laeufen mit immer gleichem
  System-Prompt bringt das spuerbare Reduktion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# USD → EUR Wechselkurs-Annahme. Wenn Foundry direkt EUR-Preise liefert,
# steht hier 1.0 (Sweden Central liefert oft USD-Listen, abgerechnet wird
# in der Vertragswaehrung). Stand-Hinweis: bei Anpassung Datum mitfuehren.
USD_TO_EUR = 0.92          # Stand 2026-04-26


@dataclass(frozen=True)
class TokenPrice:
    """Preise pro 1 Million Tokens, in EUR (nach USD→EUR-Umrechnung).

    Foundry/Azure-OpenAI gibt Preise i.d.R. in USD pro 1M Tokens an.
    Wir konvertieren beim Modul-Load mit USD_TO_EUR und speichern direkt
    EUR-Werte, damit Konsumenten nicht jedes Mal umrechnen muessen.
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


def _usd(input_usd: float, cached_usd: float, output_usd: float) -> TokenPrice:
    """Helper: USD-Listpreise → TokenPrice in EUR."""
    return TokenPrice(
        input_eur_per_1m=input_usd * USD_TO_EUR,
        cached_input_eur_per_1m=cached_usd * USD_TO_EUR,
        output_eur_per_1m=output_usd * USD_TO_EUR,
    )


# ---------------------------------------------------------------------------
# Foundry GPT-Familie
# ---------------------------------------------------------------------------
# Werte sind aktuelle Branchen-Annahmen (GPT-4o-Klasse) und konservativ
# nach oben gerundet — wenn die echten Foundry-GPT-5.1-Preise abweichen,
# bitte hier anpassen.

FOUNDRY_PRICING: dict[str, TokenPrice] = {
    # gpt-5.1: Annahme nahe gpt-4o (input $2.50, cached $1.25, output $10).
    # Wenn echte gpt-5.1-Preise hoeher sein sollten, hier ersetzen.
    "gpt-5.1": _usd(input_usd=2.50, cached_usd=1.25, output_usd=10.00),
    # gpt-5: gleiche Annahme als Fallback
    "gpt-5":   _usd(input_usd=2.50, cached_usd=1.25, output_usd=10.00),
    # gpt-4o: bekannte Listpreise
    "gpt-4o":  _usd(input_usd=2.50, cached_usd=1.25, output_usd=10.00),
}


def get_foundry_price(deployment: str) -> TokenPrice | None:
    """TokenPrice fuer ein Foundry-Deployment, oder None wenn unbekannt."""
    if deployment in FOUNDRY_PRICING:
        return FOUNDRY_PRICING[deployment]
    # Heuristik: prefix-match (z.B. 'gpt-5.1-mini' fallback auf 'gpt-5.1')
    for known, price in FOUNDRY_PRICING.items():
        if deployment.startswith(known):
            return price
    return None


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
    "USD_TO_EUR",
    "TokenPrice",
    "FOUNDRY_PRICING",
    "get_foundry_price",
    "extract_token_usage",
]
