"""Abstract LLM provider — swap implementations without changing callers."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Generate structured JSON text from a prompt."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Short id stored in DB, e.g. 'gemini'."""

    @abstractmethod
    def generate_json(self, prompt: str, *, system_instruction: str | None = None) -> str:
        """
        Call the LLM and return raw JSON string (object).
        Implementations should request JSON-only output when supported.
        """
