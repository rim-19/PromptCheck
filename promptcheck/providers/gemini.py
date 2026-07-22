"""Google Gemini provider (REST, free tier friendly)."""

from __future__ import annotations

import os
import time

import httpx

from .base import (
    GenResult,
    Provider,
    ProviderError,
    RetryableProviderError,
    parse_retry_after,
)

_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Rough USD per 1M tokens (input, output). Free tier bills $0; kept for
# cost_below assertions and reporting. Unknown models fall back to (0, 0).
_PRICES = {
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}


def _price(model: str) -> tuple[float, float]:
    for key, p in _PRICES.items():
        if model.startswith(key):
            return p
    return (0.0, 0.0)


class GeminiProvider(Provider):
    name = "gemini"

    def _api_key(self) -> str:
        key = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ProviderError(
                "GEMINI_KEY is not set. Add it to your .env "
                "(get one at https://aistudio.google.com/apikey)."
            )
        return key

    async def generate(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> GenResult:
        url = f"{_BASE}/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        start = time.perf_counter()
        try:
            resp = await client.post(
                url,
                params={"key": self._api_key()},
                json=payload,
                timeout=60.0,
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini request failed: {e}") from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableProviderError(
                f"gemini {model} returned {resp.status_code}: {resp.text[:200]}",
                retry_after=parse_retry_after(resp),
            )
        if resp.status_code != 200:
            raise ProviderError(
                f"gemini {model} returned {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()

        try:
            candidates = data["candidates"]
            parts = candidates[0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            # e.g. blocked by safety filters, or empty completion.
            reason = data.get("promptFeedback", {}).get("blockReason", "empty response")
            raise ProviderError(f"gemini {model} produced no text ({reason})")

        usage = data.get("usageMetadata", {})
        pt = int(usage.get("promptTokenCount", 0))
        ct = int(usage.get("candidatesTokenCount", 0))
        in_price, out_price = _price(model)
        cost = (pt / 1e6) * in_price + (ct / 1e6) * out_price

        return GenResult(
            text=text,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_usd=cost,
            latency_ms=latency_ms,
            model_version=str(data.get("modelVersion", model)),
        )
