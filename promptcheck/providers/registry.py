"""Maps model refs like 'gemini/gemini-2.0-flash' to a provider + model name."""

from __future__ import annotations

from .base import Provider, ProviderError
from .gemini import GeminiProvider
from .groq import GroqProvider

_PROVIDERS: dict[str, Provider] = {
    GeminiProvider.name: GeminiProvider(),
    GroqProvider.name: GroqProvider(),
}


def parse_model_ref(ref: str) -> tuple[str, str]:
    """Split 'provider/model' into ('provider', 'model')."""
    if "/" not in ref:
        raise ProviderError(
            f"model ref {ref!r} must be 'provider/model', "
            f"e.g. 'gemini/gemini-2.0-flash'. Known providers: "
            f"{', '.join(sorted(_PROVIDERS))}."
        )
    provider, _, model = ref.partition("/")
    return provider, model


def get_provider(ref: str) -> tuple[Provider, str]:
    provider_name, model = parse_model_ref(ref)
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        raise ProviderError(
            f"unknown provider {provider_name!r} in {ref!r}. "
            f"Known: {', '.join(sorted(_PROVIDERS))}."
        )
    return provider, model
