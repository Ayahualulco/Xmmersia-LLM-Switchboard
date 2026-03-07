"""
Together AI Provider Adapter
════════════════════════════
"""

from __future__ import annotations

from llm_switchboard.core.health_engine import StatusPageSignal
from llm_switchboard.providers.base import BaseProvider


class TogetherProvider(BaseProvider):
    """Adapter for Together AI (open-source model hosting)."""

    async def fetch_status(self) -> StatusPageSignal:
        url = self.config.status_api_url
        if not url:
            return StatusPageSignal(provider="together", status="unknown")

        data = await self._fetch_statuspage_json(url)
        if not data:
            return StatusPageSignal(provider="together", status="unknown")

        status = self._parse_statuspage_indicator(data)
        return StatusPageSignal(provider="together", status=status, raw_data=data)

    def list_models(self) -> list[dict]:
        return self.config.models
