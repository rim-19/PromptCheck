"""Uniform provider interface.

Every provider takes a rendered prompt + params and returns a GenResult with
the text and enough metadata (tokens, cost, latency, model version) for
assertions, cost checks, and — later — drift attribution.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


def parse_retry_after(resp: httpx.Response) -> float | None:
    """Best-effort parse of a Retry-After header (seconds)."""
    val = resp.headers.get("retry-after")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


class ProviderError(Exception):
    """A provider failed to produce a response (auth, network, API error)."""


class RetryableProviderError(ProviderError):
    """A transient failure (429 rate limit or 5xx) worth retrying.

    `retry_after` is the server-suggested wait in seconds, if any.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class GenResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    model_version: str  # exact model/version string reported by the API, for drift tracking


class Provider:
    """Base class. Subclasses implement `generate`."""

    #: provider prefix used in model refs, e.g. "gemini" in "gemini/gemini-2.0-flash"
    name: str = ""

    async def generate(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> GenResult:
        raise NotImplementedError
