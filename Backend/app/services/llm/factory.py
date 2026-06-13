"""Resolve configured LLM provider (gemini today; extend for OpenAI, etc.)."""

import os

from app.services.llm.base import LLMProvider
from app.services.llm.gemini import GeminiProvider


def get_llm_provider() -> LLMProvider:
    """
    LLM_PROVIDER env: gemini (default). Future: openai, anthropic, ...
    GEMINI_API_KEY required when provider is gemini.
    GEMINI_MODEL optional (default gemini-2.5-flash).
    """
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()

    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your environment to use IPO LLM research."
            )
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
        return GeminiProvider(api_key=api_key, model=model)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
