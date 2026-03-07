"""
Tests for Health Engine
═══════════════════════
"""

import time
import pytest

from llm_switchboard.core.health_engine import (
    CommunitySignal,
    HealthAssessment,
    HealthEngine,
    HealthStatus,
    ProbeSignal,
    Recommendation,
    StatusPageSignal,
)


# ── Test Fixtures ────────────────────────────────────────────────

MOCK_PROVIDERS = {
    "anthropic": {
        "models": [
            {"id": "claude-opus-4-6", "capabilities": ["reasoning", "coding"]},
            {"id": "claude-sonnet-4-6", "capabilities": ["reasoning", "coding"]},
        ]
    },
    "openai": {
        "models": [
            {"id": "gpt-4o", "capabilities": ["reasoning", "coding"]},
        ]
    },
}


def make_engine(**kwargs) -> HealthEngine:
    return HealthEngine(providers=MOCK_PROVIDERS, **kwargs)


# ── StatusPageSignal Tests ───────────────────────────────────────

class TestStatusPageSignal:
    def test_operational_score(self):
        signal = StatusPageSignal(provider="anthropic", status="operational")
        assert signal.score == 1.0

    def test_degraded_score(self):
        signal = StatusPageSignal(provider="anthropic", status="degraded_performance")
        assert signal.score == 0.6

    def test_major_outage_score(self):
        signal = StatusPageSignal(provider="anthropic", status="major_outage")
        assert signal.score == 0.1

    def test_unknown_status_score(self):
        signal = StatusPageSignal(provider="anthropic", status="something_new")
        assert signal.score == 0.5


# ── ProbeSignal Tests ────────────────────────────────────────────

class TestProbeSignal:
    def test_successful_fast_probe(self):
        signal = ProbeSignal(provider="anthropic", model="claude-opus-4-6",
                             success=True, latency_ms=500)
        assert signal.score == 1.0

    def test_successful_slow_probe(self):
        signal = ProbeSignal(provider="anthropic", model="claude-opus-4-6",
                             success=True, latency_ms=5000)
        assert signal.score == 0.5

    def test_failed_probe(self):
        signal = ProbeSignal(provider="anthropic", model="claude-opus-4-6",
                             success=False, latency_ms=0, error="timeout")
        assert signal.score == 0.0


# ── HealthEngine Tests ───────────────────────────────────────────

class TestHealthEngine:
    def test_unknown_model_returns_unknown(self):
        engine = make_engine()
        assessment = engine.assess("nonexistent-model")
        assert assessment.status == HealthStatus.UNKNOWN
        assert assessment.confidence == 0.1

    def test_no_signals_returns_uncertain(self):
        engine = make_engine()
        assessment = engine.assess("claude-opus-4-6")
        # No signals loaded — should be uncertain
        assert assessment.confidence <= 0.2

    def test_healthy_status_page(self):
        engine = make_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="operational")
        )
        assessment = engine.assess("claude-opus-4-6")
        assert assessment.status == HealthStatus.HEALTHY
        assert assessment.score >= 0.7

    def test_degraded_status_page(self):
        engine = make_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="degraded_performance")
        )
        assessment = engine.assess("claude-opus-4-6")
        assert assessment.status == HealthStatus.DEGRADED

    def test_major_outage(self):
        engine = make_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="major_outage")
        )
        assessment = engine.assess("claude-opus-4-6")
        assert assessment.status == HealthStatus.DOWN

    def test_probe_overrides_status_page(self):
        engine = make_engine()
        # Status page says operational
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="operational")
        )
        # But probe shows failure
        engine.update_probe_signal(
            ProbeSignal(provider="anthropic", model="claude-opus-4-6",
                        success=False, latency_ms=0, error="500 error")
        )
        assessment = engine.assess("claude-opus-4-6")
        # Combined score should be lower than pure status page
        assert assessment.score < 1.0

    def test_caching_works(self):
        engine = make_engine(cache_ttl=10)
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="operational")
        )
        # First call computes
        a1 = engine.assess("claude-opus-4-6")
        # Second call should be cached (same object)
        a2 = engine.assess("claude-opus-4-6")
        assert a1 is a2

    def test_invalidation_on_signal_update(self):
        engine = make_engine(cache_ttl=10)
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="operational")
        )
        a1 = engine.assess("claude-opus-4-6")
        assert a1.status == HealthStatus.HEALTHY

        # Update signal — should invalidate cache
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="major_outage")
        )
        a2 = engine.assess("claude-opus-4-6")
        assert a2.status == HealthStatus.DOWN
        assert a1 is not a2

    def test_get_all_assessments(self):
        engine = make_engine()
        assessments = engine.get_all_assessments()
        # Should have entries for all 3 models in MOCK_PROVIDERS
        assert len(assessments) == 3
        assert "claude-opus-4-6" in assessments
        assert "gpt-4o" in assessments

    def test_assessment_to_dict(self):
        engine = make_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="operational")
        )
        assessment = engine.assess("claude-opus-4-6")
        d = assessment.to_dict()
        assert d["model"] == "claude-opus-4-6"
        assert d["provider"] == "anthropic"
        assert d["status"] == "healthy"
        assert "score" in d
        assert "confidence" in d
