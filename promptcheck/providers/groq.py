"""Groq provider (OpenAI-compatible chat completions, free tier)."""

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

_URL = "https://api.groq.com/openai/v1/chat/completions"

# Groq's hosted open models are free to call; prices kept at 0 but the
# structure mirrors gemini.py so paid models can be added later.
_PRICES: dict[str, tuple[float, float]] = {}


def _price(model: str) -> tuple[float, float]:
    for key, p in _PRICES.items():
        if model.startswith(key):
            return p
    return (0.0, 0.0)


class GroqProvider(Provider):
    name = "groq"

    def _api_key(self) -> str:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ProviderError(
                "GROQ_API_KEY is not set. Add it to your .env "
                "(get one at https://console.groq.com/keys)."
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
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._api_key()}"}
        start = time.perf_counter()
        try:
            resp = await client.post(_URL, json=payload, headers=headers, timeout=60.0)
        except httpx.HTTPError as e:
            raise ProviderError(f"groq request failed: {e}") from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableProviderError(
                f"groq {model} returned {resp.status_code}: {resp.text[:200]}",
                retry_after=parse_retry_after(resp),
            )
        if resp.status_code != 200:
            raise ProviderError(
                f"groq {model} returned {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()

        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise ProviderError(f"groq {model} produced no text: {e}") from e

        usage = data.get("usage", {})
        pt = int(usage.get("prompt_tokens", 0))
        ct = int(usage.get("completion_tokens", 0))
        in_price, out_price = _price(model)
        cost = (pt / 1e6) * in_price + (ct / 1e6) * out_price

        return GenResult(
            text=text,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_usd=cost,
            latency_ms=latency_ms,
            model_version=str(data.get("model", model)),
        )
