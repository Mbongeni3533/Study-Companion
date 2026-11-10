"""Optional LLM provider with a graceful no-key fallback.

The whole product must work with zero external services, so this module never
raises on a missing key or a failed call: it returns ``None`` and the caller
falls back to the deterministic rule engine in ``ai_coach.py``.

Model calls go through an in-process `Respan Gateway
<https://github.com/respanai/respan-gateway>`_. The gateway is the single place
that holds the provider key and decides where a model request goes: the coach
asks for the ``study-coach`` route, which the gateway maps to the configured
Anthropic model (with retries and room for a fallback). Pointing
``ANTHROPIC_BASE_URL`` at another endpoint therefore moves every coach call
without touching this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
import respan_gateway as rg

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

# The route the coach asks for; the gateway resolves it to a real provider model.
COACH_ROUTE = "study-coach"


def gateway_config(
    *, api_key: str, model: str, base_url: str | None = None
) -> dict[str, Any]:
    """Gateway config for the app: one Anthropic provider behind one route.

    The key is passed in memory from the app settings (which read the ignored
    ``.env``), never written to a file.
    """
    provider: dict[str, Any] = {"vendor": "anthropic", "key": api_key}
    if base_url:
        provider["base_url"] = base_url
    return {
        "log": "off",
        "ui": False,
        "providers": {"anthropic": provider},
        "routes": {COACH_ROUTE: {"to": [f"anthropic/{model}"], "tries": 2}},
    }


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
    """Anthropic Messages API through the in-process Respan gateway."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 45.0,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = base_url

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 1000,
    ) -> str | None:
        payload = {
            "model": COACH_ROUTE,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [
                {"role": m.role, "content": [{"type": "text", "text": m.content}]}
                for m in messages
                if m.role in {"user", "assistant"}
            ],
        }
        # The gateway authenticates the provider call, so no key is sent from here.
        headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        config = gateway_config(
            api_key=self._api_key, model=self.model, base_url=self.base_url
        )
        try:
            async with rg.Gateway(config=config) as gateway:
                async with httpx.AsyncClient(
                    base_url="http://respan-gateway",
                    timeout=self.timeout,
                    transport=gateway.async_transport(),
                ) as client:
                    response = await client.post("/v1/messages", json=payload, headers=headers)
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
            base_url=settings.anthropic_base_url,
        )
    return None
