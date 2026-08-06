"""
Tests for the Trust Tier Gate
══════════════════════════════
Gate table: L'Atelier llm-switchboard §06.

Note on the fixture: HealthEngine scores a model with no signals at 0.5,
which classifies as *degraded*, not healthy. Every test here needs the
health axis held at "healthy" so that what it observes is the trust gate
and nothing else — hence the explicit operational signals below.
"""

import pytest

from llm_switchboard.core.health_engine import HealthEngine, StatusPageSignal
from llm_switchboard.core.router import Router
from llm_switchboard.policies import FAST, CAREFUL, CRITICAL


TRUST_PROVIDERS = {
    "anthropic": {
        "models": [
            {"id": "claude-opus-4-6", "capabilities": ["reasoning"],
             "tier": "flagship", "context_window": 200000},
        ]
    },
    "xai": {
        "models": [
            {"id": "grok-build-0.1", "capabilities": ["reasoning"],
             "tier": "reasoning_fast", "context_window": 256000,
             "trust_tier": "watched"},
            {"id": "grok-untested", "capabilities": ["reasoning"],
             "tier": "reasoning_fast", "context_window": 256000,
             "trust_tier": "untrusted"},
        ]
    },
}


def make_router_and_engine():
    engine = HealthEngine(providers=TRUST_PROVIDERS)
    # Hold the health axis at "healthy" so only the trust gate can move a decision
    for provider in TRUST_PROVIDERS:
        engine.update_status_signal(
            StatusPageSignal(provider=provider, status="operational")
        )
    router = Router(health_engine=engine, providers=TRUST_PROVIDERS)
    return router, engine


class TestTrustGateWatched:
    def test_watched_refused_under_critical(self):
        router, _ = make_router_and_engine()
        result = router.route("grok-build-0.1", policy=CRITICAL)
        # Refused on trust despite being healthy; a Trusted healthy model exists,
        # so the gate reroutes rather than stops.
        assert result.routed_to != "grok-build-0.1"
        assert result.action == "rerouted"
        assert "trust_tier=watched" in result.reason

    def test_watched_allowed_under_careful(self):
        router, _ = make_router_and_engine()
        result = router.route("grok-build-0.1", policy=CAREFUL)
        assert result.action == "proceed"
        assert result.routed_to == "grok-build-0.1"

    def test_watched_allowed_under_fast(self):
        router, _ = make_router_and_engine()
        result = router.route("grok-build-0.1", policy=FAST)
        assert result.action == "proceed"


class TestTrustGateUntrusted:
    def test_untrusted_refused_under_careful(self):
        router, _ = make_router_and_engine()
        result = router.route("grok-untested", policy=CAREFUL)
        assert result.routed_to != "grok-untested"
        assert "trust_tier=untrusted" in result.reason

    def test_untrusted_refused_under_critical(self):
        router, _ = make_router_and_engine()
        result = router.route("grok-untested", policy=CRITICAL)
        assert result.routed_to != "grok-untested"
        assert "trust_tier=untrusted" in result.reason

    def test_untrusted_refused_under_fast_learner_facing_default(self):
        router, _ = make_router_and_engine()
        result = router.route("grok-untested", policy=FAST)
        assert result.routed_to != "grok-untested"
        assert "trust_tier=untrusted" in result.reason

    def test_untrusted_allowed_under_fast_non_learner_facing(self):
        router, _ = make_router_and_engine()
        policy = dict(FAST, learner_facing=False)
        result = router.route("grok-untested", policy=policy)
        assert result.action == "proceed"
        assert result.routed_to == "grok-untested"


class TestTrustGateTrustedUnaffected:
    def test_trusted_model_unaffected_by_gate(self):
        router, _ = make_router_and_engine()
        result = router.route("claude-opus-4-6", policy=CRITICAL)
        assert result.action == "proceed"


class TestTrustGateRerouteOrStop:
    def test_refused_model_reroutes_to_trusted_alternative(self):
        router, engine = make_router_and_engine()
        policy = {
            "criticality": "critical",
            "on_degraded": "stop", "on_down": "stop",
            "acceptable_models": ["claude-opus-4-6"],
            "min_status": "healthy",
        }
        result = router.route("grok-build-0.1", policy=policy)
        assert result.action == "rerouted"
        assert result.routed_to == "claude-opus-4-6"

    def test_refused_model_stops_with_no_alternative(self):
        # The only alternative offered is itself trust-ineligible under CRITICAL,
        # so the gate has nowhere to go and must stop.
        router, engine = make_router_and_engine()
        policy = {
            "criticality": "critical",
            "on_degraded": "stop", "on_down": "stop",
            "acceptable_models": ["grok-untested"],
            "min_status": "healthy",
        }
        result = router.route("grok-build-0.1", policy=policy)
        assert result.action == "stopped"
        assert result.routed_to == "grok-build-0.1"

    def test_alternative_search_never_reroutes_to_untrusted(self):
        # A CRITICAL request for a *down* trusted model must not reroute to
        # an untrusted candidate purely because it's the only one healthy.
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="major_outage")
        )
        policy = {
            "criticality": "critical",
            "on_degraded": "stop", "on_down": "reroute",
            "acceptable_models": ["claude-opus-4-6", "grok-untested"],
            "min_status": "healthy",
        }
        result = router.route("claude-opus-4-6", policy=policy)
        assert result.action == "stopped"
        assert result.routed_to == "claude-opus-4-6"
        assert "grok-untested" not in result.alternatives_checked


class TestTrustGateUnknownTier:
    def test_unknown_trust_tier_treated_as_untrusted(self):
        providers = {
            "test": {"models": [
                {"id": "mystery-model", "capabilities": [], "tier": "balanced",
                 "context_window": 100000, "trust_tier": "bogus"},
            ]}
        }
        engine = HealthEngine(providers=providers)
        engine.update_status_signal(
            StatusPageSignal(provider="test", status="operational")
        )
        router = Router(health_engine=engine, providers=providers)
        result = router.route("mystery-model", policy=CAREFUL)
        assert result.action == "stopped"
        # The gate treats it as untrusted, but the reason records the tier as
        # actually configured — provenance should show the real bad value.
        assert "trust_tier=bogus" in result.reason
