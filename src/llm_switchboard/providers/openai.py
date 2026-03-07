"""
OpenAI Provider Adapter
═══════════════════════

Fetches health from status.openai.com and optionally probes the API.
"""

from __future__ import annotations

import logging
import time

from llm_switchboard.core.health_engine import ProbeSignal, StatusPageSignal
from llm_switchboard.providers.base import BaseProvider


logger = logging.getLogger("llm_switchboard.providers.openai")


class OpenAIProvider(BaseProvider):
    """Adapter for OpenAI (GPT models)."""

    async def fetch_status(self) -> StatusPageSignal:
        """Fetch status from status.openai.com."""
        url = self.config.status_api_url
        if not url:
            return StatusPageSignal(
                provider="openai",
                status="unknown",
                description="No status API URL configured",
            )

        data = await self._fetch_statuspage_json(url)
        if not data:
            return StatusPageSignal(
                provider="openai",
                status="unknown",
                description="Failed to fetch status page",
            )

        status = self._parse_statuspage_indicator(data)
        components = self._parse_statuspage_components(data)
        description = data.get("status", {}).get("description", "")
        affected = [
            c["name"] for c in components
            if c.get("status") != "operational"
        ]

        return StatusPageSignal(
            provider="openai",
            status=status,
            description=description,
            affected_components=affected,
            raw_data=data,
        )

    def list_models(self) -> list[dict]:
        """Return OpenAI's model catalog."""
        return self.config.models

    async def probe(self, model: str) -> ProbeSignal | None:
        """Send a lightweight test request to OpenAI's API."""
        if not self._api_key:
            return None

        start = time.time()
        try:
            response = await self._client.post(
                f"{self.config.api_base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 5,
                    "messages": [
                        {"role": "user", "content": "Say 'ok' and nothing else."}
                    ],
                },
                timeout=15.0,
            )
            latency_ms = (time.time() - start) * 1000

            return ProbeSignal(
                provider="openai",
                model=model,
                success=response.status_code == 200,
                latency_ms=latency_ms,
                error=(
                    f"HTTP {response.status_code}" if response.status_code != 200 else None
                ),
            )

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return ProbeSignal(
                provider="openai",
                model=model,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )
