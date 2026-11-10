"""Optional LLM provider with a graceful no-key fallback.

The whole product must work with zero external services, so this module never
raises on a missing key or a failed call: it returns ``None`` and the caller
falls back to the deterministic rule engine in ``ai_coach.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


class AIProvider:
    """Base class for chat-completion providers."""

    name = "base"

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
    ) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError


class ClaudeProvider(AIProvider):
    """Anthropic Messages API over plain HTTP (no SDK dependency)."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = 45.0) -> None:
        self._api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
    ) -> str | None:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [
                {"role": m.role, "content": [{"type": "text", "text": m.content}]}
                for m in messages
                if m.role in {"user", "assistant"}
            ],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages", json=payload, headers=headers
                )
            if response.status_code >= 400:
                logger.warning(
                    "AI provider returned %s: %s", response.status_code, response.text[:300]
                )
                return None
            data = response.json()
            parts = [
                block.get("text", "")
                for block in data.get("content", [])
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            text = "".join(parts).strip()
            return text or None
        except Exception as exc:  # noqa: BLE001 - never break a request over AI
            logger.warning("AI provider call failed: %s", exc)
            return None


def build_provider(settings: Settings | None = None) -> AIProvider | None:
    settings = settings or get_settings()
    if settings.anthropic_api_key:
        return ClaudeProvider(
            settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout=settings.ai_timeout_seconds,
        )
    return None
