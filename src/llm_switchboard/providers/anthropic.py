"""
Anthropic Provider Adapter
══════════════════════════

Fetches health from status.anthropic.com and optionally probes the API.
"""

from __future__ import annotations

import logging
import time

from llm_switchboard.core.health_engine import ProbeSignal, StatusPageSignal
from llm_switchboard.providers.base import BaseProvider, ProviderConfig


logger = logging.getLogger("llm_switchboard.providers.anthropic")


class AnthropicProvider(BaseProvider):
    """Adapter for Anthropic (Claude models)."""

    async def fetch_status(self) -> StatusPageSignal:
        """Fetch status from status.anthropic.com."""
        url = self.config.status_api_url
        if not url:
            return StatusPageSignal(
                provider="anthropic",
                status="unknown",
                description="No status API URL configured",
            )

        data = await self._fetch_statuspage_json(url)
        if not data:
            return StatusPageSignal(
                provider="anthropic",
                status="unknown",
                description="Failed to fetch status page",
            )

        status = self._parse_statuspage_indicator(data)
        components = self._parse_statuspage_components(data)
        description = data.get("status", {}).get("description", "")

        # Check specifically for API component
        api_components = [
            c for c in components
            if "api" in c.get("name", "").lower()
        ]
        affected = [
            c["name"] for c in components
            if c.get("status") != "operational"
        ]

        return StatusPageSignal(
            provider="anthropic",
            status=status,
            description=description,
            affected_components=affected,
            raw_data=data,
        )

    def list_models(self) -> list[dict]:
        """Return Anthropic's model catalog."""
        return self.config.models

    async def probe(self, model: str) -> ProbeSignal | None:
        """
        Send a lightweight test request to Anthropic's API.

        Requires ANTHROPIC_API_KEY to be configured.
        """
        if not self._api_key:
            return None

        start = time.time()
        try:
            response = await self._client.post(
                f"{self.config.api_base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
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

            if response.status_code == 200:
                return ProbeSignal(
                    provider="anthropic",
                    model=model,
                    success=True,
                    latency_ms=latency_ms,
                )
            else:
                return ProbeSignal(
                    provider="anthropic",
                    model=model,
                    success=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return ProbeSignal(
                provider="anthropic",
                model=model,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )
