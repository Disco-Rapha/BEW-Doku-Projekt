"""Zentrale Foundry-/Azure-Pricing-Konstanten in EUR.

EINE Source-of-Truth fuer alle Cost-Berechnungen — Image-Engine, Flow-LLM-
Calls, Chat-Cost-Tracking. Alle anderen Module rufen `get_foundry_price()`
oder `compute_cost_eur()` und bekommen identische Werte.

Werte sind die Sweden Central Data Zone Standard-Listpreise in EUR pro
1M Tokens (das Tier in dem unsere Foundry-Resource liegt). Microsoft
publiziert das direkt in EUR — keine USD→EUR-Umrechnung noetig.

WICHTIG — Konvention: 1 Pricing pro Deployment, kein Prefix-Matching
================================================================
Jeder Eintrag ist auf einen **konkreten Deployment-Namen** gemappt
(wie er im Foundry-Portal steht), nicht auf die Modell-Familie. Das
verhindert Drift wenn ein Deployment mal abweichende Tier-Werte hat
(z.B. wenn jemand "gpt-5.4-test" mit anderem Pricing deployed).

Wenn du ein neues Deployment anlegst:
  1. Foundry-Portal: Deployment-Name vergeben, z.B. "gpt-5.4-test"
  2. Hier den entsprechenden Eintrag mit den echten Preisen ergaenzen
  3. Bei unbekanntem Deployment liefert get_foundry_price() None
     und compute_cost_eur() gibt 0.0 EUR + Log-Warning zurueck

WICHTIG — Werte regelmaessig pruefen:
  - https://azure.microsoft.com/de-de/pricing/details/ai-foundry/
  - Region "Sweden Central" + Tier "Data Zone Standard"
  - Stand 2026-04-29 (BEW): bei Aenderung Datum hochziehen.

Cached-Input-Discount:
  Foundry/Azure-OpenAI cacht den System-Prompt-Praefix ueber Calls
  hinweg (typisch >50% des Inputs). Bei gpt-5.1: ~50% Rabatt vom
  Input-Preis. Bei gpt-5.4: 90% Rabatt (also nur 10% des Input-Preises).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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
# Foundry-Deployments — 1:1 Pricing
# ---------------------------------------------------------------------------
# Genau die Deployments, die im Foundry-Portal "Sweden-central-deployment"
# existieren. Erweiterung pro neuem Deployment hier eintragen.

FOUNDRY_PRICING: dict[str, TokenPrice] = {
    # Deployment: gpt-5.1
    # Modell:     gpt-5.1
    # Tier:       Data Zone Standard (Sweden Central)
    # Quelle:     User-Verifikation gegen Microsoft-Pricing-Seite
    #             am 2026-05-06 (Screenshot). Microsoft publiziert
    #             EUR-Listpreise direkt — keine USD-Umrechnung noetig.
    # Cached:     ~90% Rabatt (0.12 / 1.18 = 10.2%). Identische Mechanik
    #             wie bei gpt-5.4 (0.23 / 2.30 = 10%).
    "gpt-5.1": TokenPrice(
        input_eur_per_1m=1.18,
        cached_input_eur_per_1m=0.12,
        output_eur_per_1m=9.41,
    ),

    # Deployment: gpt-5.1_prod
    # Modell:     gpt-5.1 (alter Prod-Alias, vor "gpt-5.4-prod"-Migration)
    # Werte:     identisch zu gpt-5.1
    "gpt-5.1_prod": TokenPrice(
        input_eur_per_1m=1.18,
        cached_input_eur_per_1m=0.12,
        output_eur_per_1m=9.41,
    ),

    # Deployment: gpt-5.4-prod
    # Modell:     gpt-5.4
    # Tier:       Data Zone Standard (Sweden Central) — wird von uns
    #             benutzt, ist von Microsoft aber noch NICHT separat
    #             publiziert (Stand 2026-05-06).
    # Quelle:     Extrapoliert aus Microsoft-publiziertem Global-Tarif
    #             (Global: 2.14 / 0.22 / 12.82) mit dem empirischen
    #             Aufschlag aus gpt-5.1 (Global→Data-Zone ~+10%):
    #               Input  2.14 * 1.103 ≈ 2.36
    #               Cached 0.22 * 1.091 ≈ 0.24
    #               Output 12.82 * 1.101 ≈ 14.10
    # WICHTIG:    Sobald Microsoft den Data-Zone-Tarif publiziert,
    #             gegen die Liste verifizieren. Alte Werte vom
    #             2026-04-27 (2.30 / 0.23 / 14.50) waren freie
    #             User-Schaetzung — die aktualisierten Werte sind
    #             besser begruendet.
    "gpt-5.4-prod": TokenPrice(
        input_eur_per_1m=2.36,
        cached_input_eur_per_1m=0.24,
        output_eur_per_1m=14.10,
    ),
}


def get_foundry_price(deployment: str) -> TokenPrice | None:
    """TokenPrice fuer ein Foundry-Deployment, oder None wenn unbekannt.

    EXACT-MATCH only — kein Prefix-Matching. Wenn ein Deployment nicht
    in FOUNDRY_PRICING steht, ist es ein Konfig-Fehler (Deployment im
    Foundry-Portal angelegt, aber nicht in pricing.py ergaenzt).

    Caller sollten None als "unbekannt → 0 EUR + Warning loggen"
    behandeln, nicht stillschweigend.
    """
    if deployment in FOUNDRY_PRICING:
        return FOUNDRY_PRICING[deployment]
    logger.warning(
        "Kein Pricing fuer Deployment %r — bitte in disco/pricing.py "
        "FOUNDRY_PRICING ergaenzen. Cost-Tracking liefert 0.0 EUR.",
        deployment,
    )
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
    Deployment nicht in FOUNDRY_PRICING ist, wird 0.0 zurueckgegeben
    (Warning bereits in get_foundry_price geloggt).
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
