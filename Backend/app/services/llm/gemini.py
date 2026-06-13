"""Google Gemini generateContent API."""

from __future__ import annotations

import logging

import requests

from app.services.llm.base import LLMProvider
from app.utils.network import make_requests_session

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def provider_id(self) -> str:
        return "gemini"

    def generate_json(self, prompt: str, *, system_instruction: str | None = None) -> str:
        url = f"{GEMINI_API_BASE}/{self._model}:generateContent"
        body: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        session = make_requests_session()
        response = session.post(
            url,
            params={"key": self._api_key},
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        if response.status_code != 200:
            logger.error("Gemini API error %s: %s", response.status_code, response.text[:500])
            if response.status_code == 429:
                raise ValueError(
                    f"Gemini quota exceeded for model '{self._model}'. "
                    "Your free tier may not include this model (gemini-2.0-flash often shows limit: 0). "
                    "Set GEMINI_MODEL=gemini-2.5-flash or gemini-3.5-flash in Backend/.env and restart."
                )
            response.raise_for_status()

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        if not parts or "text" not in parts[0]:
            raise ValueError("Gemini response missing text")
        return parts[0]["text"].strip()
