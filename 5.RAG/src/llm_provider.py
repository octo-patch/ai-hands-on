"""Cloud LLM provider for RAG answer generation.

Supports MiniMax, OpenAI, and any OpenAI-compatible API as an alternative
to local BART generation. Provider is auto-detected from environment
variables or can be explicitly configured.
"""

import os
from dataclasses import dataclass

# Provider presets: name -> (base_url, default_model, env_key)
PROVIDER_PRESETS = {
    "minimax": {
        "base_url": "https://api.minimax.io/v1",
        "default_model": "MiniMax-M2.7",
        "env_key": "MINIMAX_API_KEY",
        "display_name": "MiniMax",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "display_name": "OpenAI",
    },
}

# Auto-detection order: try MiniMax first, then OpenAI
_DETECTION_ORDER = ["minimax", "openai"]


@dataclass
class LLMConfig:
    """Configuration for a cloud LLM provider."""

    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 1024


def detect_provider():
    """Auto-detect available LLM provider from environment variables.

    Returns the provider name (e.g. ``"minimax"``) or ``None`` if no API key
    is found.
    """
    for name in _DETECTION_ORDER:
        preset = PROVIDER_PRESETS[name]
        if os.environ.get(preset["env_key"]):
            return name
    return None


def get_llm_config(
    provider=None,
    model=None,
    temperature=0.7,
    max_tokens=1024,
):
    """Build an :class:`LLMConfig` for the given or auto-detected provider.

    Parameters
    ----------
    provider : str, optional
        Provider name (``"minimax"`` or ``"openai"``).  When *None*, the
        provider is auto-detected from environment variables.
    model : str, optional
        Model identifier.  Defaults to the provider preset.
    temperature : float
        Sampling temperature.  Clamped to ``(0, 1]`` for MiniMax.
    max_tokens : int
        Maximum tokens in the completion.

    Returns
    -------
    LLMConfig or None
        ``None`` when no provider could be resolved.
    """
    if provider is None:
        provider = detect_provider()
    if provider is None:
        return None

    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        return None

    api_key = os.environ.get(preset["env_key"], "")
    if not api_key:
        return None

    resolved_model = model or preset["default_model"]

    # MiniMax temperature must be in (0, 1]
    if provider == "minimax":
        temperature = max(0.01, min(temperature, 1.0))

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        base_url=preset["base_url"],
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _strip_think_tags(text):
    """Remove ``<think>...</think>`` blocks that some models emit."""
    import re

    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def chat_completion(config, messages):
    """Send a chat completion request and return the assistant message text.

    Uses the ``openai`` Python SDK so any OpenAI-compatible endpoint works.

    Parameters
    ----------
    config : LLMConfig
        Provider configuration.
    messages : list[dict]
        Chat messages in the ``[{"role": ..., "content": ...}]`` format.

    Returns
    -------
    str
        The assistant's reply.
    """
    from openai import OpenAI

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    response = client.chat.completions.create(
        model=config.model,
        messages=messages,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    text = response.choices[0].message.content or ""
    return _strip_think_tags(text)
