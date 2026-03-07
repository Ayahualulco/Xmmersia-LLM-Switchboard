"""
Health Engine
═════════════

The brain of LLM-Switchboard. Aggregates signals from multiple sources
(status pages, active probes, community feeds), scores them, and produces
a unified health assessment per model.

The key insight: check BEFORE you call, not after you fail.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from llm_switchboard.config import defaults
from llm_switchboard.core.cache import HealthCache


logger = logging.getLogger("llm_switchboard.health")


# ── Health Status Enum ───────────────────────────────────────────

class HealthStatus(str, Enum):
    """Provider/model health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class Recommendation(str, Enum):
    """What we recommend doing given the health status."""
    PROCEED = "proceed"
    CAUTION = "caution"
    REROUTE = "reroute"
    STOP = "stop"


# ── Data Classes ─────────────────────────────────────────────────

@dataclass
class StatusPageSignal:
    """Signal from a provider's status page."""
    provider: str
    status: str               # operational, degraded_performance, partial_outage, major_outage
    description: str = ""
    affected_components: list[str] = field(default_factory=list)
    fetched_at: float = field(default_factory=time.time)
    raw_data: dict = field(default_factory=dict)

    @property
    def score(self) -> float:
        """Convert status page status to a 0-1 score."""
        mapping = {
            "operational": 1.0,
            "degraded_performance": 0.6,
            "partial_outage": 0.4,
            "minor_outage": 0.5,
            "major_outage": 0.1,
            "maintenance": 0.7,
        }
        return mapping.get(self.status.lower(), 0.5)


@dataclass
class ProbeSignal:
    """Signal from an active probe (test request to the provider)."""
    provider: str
    model: str
    success: bool
    latency_ms: float
    error: str | None = None
    probed_at: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        """Convert probe result to a 0-1 score."""
        if not self.success:
            return 0.0
        # Latency scoring: < 1s = great, < 3s = ok, < 10s = degraded, > 10s = bad
        if self.latency_ms < 1000:
            return 1.0
        elif self.latency_ms < 3000:
            return 0.8
        elif self.latency_ms < 10000:
            return 0.5
        else:
            return 0.2


@dataclass
class CommunitySignal:
    """Signal from community reports (future feature)."""
    provider: str
    report_count: int = 0
    sentiment: float = 1.0    # 0-1, where 1 = no problems reported
    fetched_at: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        """Convert community signals to a 0-1 score."""
        if self.report_count == 0:
            return 1.0
        elif self.report_count <= 2:
            return 0.7
        elif self.report_count <= 5:
            return 0.4
        else:
            return 0.2


@dataclass
class HealthAssessment:
    """The final health assessment for a model."""
    model: str
    provider: str
    status: HealthStatus
    score: float                          # 0-1 composite score
    confidence: float                     # 0-1 how sure we are
    recommendation: Recommendation
    latency_ms: float | None = None       # From probe, if available
    status_page: str = "unknown"          # Raw status page status
    community_signals: int = 0            # Number of community reports
    checked_at: str = ""                  # ISO timestamp
    alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary (for API responses and stamps)."""
        return {
            "model": self.model,
            "provider": self.provider,
            "status": self.status.value,
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 2),
            "recommendation": self.recommendation.value,
            "latency_ms": self.latency_ms,
            "status_page": self.status_page,
            "community_signals": self.community_signals,
            "checked_at": self.checked_at,
            "alternatives": self.alternatives,
        }


# ── Health Engine ────────────────────────────────────────────────

class HealthEngine:
    """
    Aggregates health signals and produces assessments.

    The engine maintains a cache of recent health checks and
    combines signals from status pages, probes, and community
    reports into a single score per provider/model.
    """

    def __init__(
        self,
        providers: dict[str, Any] | None = None,
        cache_ttl: float = defaults.DEFAULT_CACHE_TTL,
        status_page_weight: float = defaults.STATUS_PAGE_WEIGHT,
        probe_weight: float = defaults.PROBE_WEIGHT,
        community_weight: float = defaults.COMMUNITY_WEIGHT,
    ):
        self._providers = providers or {}
        self._cache = HealthCache(default_ttl=cache_ttl)
        self._weights = {
            "status_page": status_page_weight,
            "probe": probe_weight,
            "community": community_weight,
        }
        # Signal stores
        self._status_signals: dict[str, StatusPageSignal] = {}
        self._probe_signals: dict[str, ProbeSignal] = {}
        self._community_signals: dict[str, CommunitySignal] = {}

    def assess(self, model: str) -> HealthAssessment:
        """
        Get the health assessment for a model.

        Checks cache first, then computes from available signals.
        This is the primary public method.
        """
        # Check cache
        cached = self._cache.get(f"assessment:{model}")
        if cached is not None:
            return cached

        # Find the provider for this model
        provider_name = self._provider_for_model(model)
        if provider_name is None:
            return self._unknown_assessment(model)

        # Gather signals
        status_signal = self._status_signals.get(provider_name)
        probe_signal = self._probe_signals.get(model)
        community_signal = self._community_signals.get(provider_name)

        # Compute composite score
        score, confidence = self._compute_score(
            status_signal, probe_signal, community_signal
        )

        # Classify
        status = self._classify(score)
        recommendation = self._recommend(status)

        assessment = HealthAssessment(
            model=model,
            provider=provider_name,
            status=status,
            score=score,
            confidence=confidence,
            recommendation=recommendation,
            latency_ms=probe_signal.latency_ms if probe_signal else None,
            status_page=status_signal.status if status_signal else "unknown",
            community_signals=community_signal.report_count if community_signal else 0,
            checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # Cache the result
        self._cache.set(f"assessment:{model}", assessment)

        return assessment

    def update_status_signal(self, signal: StatusPageSignal) -> None:
        """Update the status page signal for a provider."""
        self._status_signals[signal.provider] = signal
        # Invalidate cached assessments for this provider's models
        self._invalidate_provider(signal.provider)

    def update_probe_signal(self, signal: ProbeSignal) -> None:
        """Update the probe signal for a specific model."""
        self._probe_signals[signal.model] = signal
        self._cache.invalidate(f"assessment:{signal.model}")

    def update_community_signal(self, signal: CommunitySignal) -> None:
        """Update community signal for a provider."""
        self._community_signals[signal.provider] = signal
        self._invalidate_provider(signal.provider)

    def get_all_assessments(self) -> dict[str, HealthAssessment]:
        """Get health assessments for all known models."""
        assessments = {}
        for provider_name, provider_config in self._providers.items():
            for model_info in provider_config.get("models", []):
                model_id = model_info["id"]
                assessments[model_id] = self.assess(model_id)
        return assessments

    # ── Private Methods ──────────────────────────────────────────

    def _provider_for_model(self, model: str) -> str | None:
        """Find which provider owns a given model."""
        for provider_name, provider_config in self._providers.items():
            for model_info in provider_config.get("models", []):
                if model_info["id"] == model:
                    return provider_name
        return None

    def _compute_score(
        self,
        status: StatusPageSignal | None,
        probe: ProbeSignal | None,
        community: CommunitySignal | None,
    ) -> tuple[float, float]:
        """
        Compute a weighted composite score and confidence level.

        Returns (score, confidence) where both are 0-1.
        Confidence depends on how many signal sources we have.
        """
        total_weight = 0.0
        weighted_sum = 0.0
        signals_available = 0

        if status is not None:
            w = self._weights["status_page"]
            weighted_sum += status.score * w
            total_weight += w
            signals_available += 1

        if probe is not None:
            w = self._weights["probe"]
            weighted_sum += probe.score * w
            total_weight += w
            signals_available += 1

        if community is not None:
            w = self._weights["community"]
            weighted_sum += community.score * w
            total_weight += w
            signals_available += 1

        if total_weight == 0:
            return 0.5, 0.1  # No signals → uncertain

        score = weighted_sum / total_weight

        # Confidence: more signals = more confident
        if signals_available >= 3:
            confidence = defaults.HIGH_CONFIDENCE
        elif signals_available == 2:
            confidence = defaults.MEDIUM_CONFIDENCE
        elif signals_available == 1:
            confidence = defaults.LOW_CONFIDENCE
        else:
            confidence = 0.1

        return score, confidence

    def _classify(self, score: float) -> HealthStatus:
        """Classify a score into a health status."""
        if score >= defaults.HEALTHY_THRESHOLD:
            return HealthStatus.HEALTHY
        elif score >= defaults.DEGRADED_THRESHOLD:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.DOWN

    def _recommend(self, status: HealthStatus) -> Recommendation:
        """Default recommendation based on health status."""
        mapping = {
            HealthStatus.HEALTHY: Recommendation.PROCEED,
            HealthStatus.DEGRADED: Recommendation.CAUTION,
            HealthStatus.DOWN: Recommendation.REROUTE,
            HealthStatus.UNKNOWN: Recommendation.CAUTION,
        }
        return mapping.get(status, Recommendation.CAUTION)

    def _unknown_assessment(self, model: str) -> HealthAssessment:
        """Return an unknown assessment for an unrecognized model."""
        return HealthAssessment(
            model=model,
            provider="unknown",
            status=HealthStatus.UNKNOWN,
            score=0.5,
            confidence=0.1,
            recommendation=Recommendation.CAUTION,
            checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _invalidate_provider(self, provider_name: str) -> None:
        """Invalidate cached assessments for all models of a provider."""
        provider_config = self._providers.get(provider_name, {})
        for model_info in provider_config.get("models", []):
            self._cache.invalidate(f"assessment:{model_info['id']}")
