"""
Tests for Router
════════════════
"""

import pytest

from llm_switchboard.core.health_engine import (
    HealthEngine,
    HealthStatus,
    StatusPageSignal,
)
from llm_switchboard.core.router import Router, RoutingResult
from llm_switchboard.policies import FAST, CAREFUL, CRITICAL


MOCK_PROVIDERS = {
    "anthropic": {
        "models": [
            {"id": "claude-opus-4-6", "capabilities": ["reasoning", "coding", "analysis"],
             "tier": "flagship", "context_window": 200000},
            {"id": "claude-sonnet-4-6", "capabilities": ["reasoning", "coding", "analysis"],
             "tier": "balanced", "context_window": 200000},
        ]
    },
    "openai": {
        "models": [
            {"id": "gpt-4o", "capabilities": ["reasoning", "coding", "analysis"],
             "tier": "flagship", "context_window": 128000},
        ]
    },
}


def make_router_and_engine():
    engine = HealthEngine(providers=MOCK_PROVIDERS)
    router = Router(health_engine=engine, providers=MOCK_PROVIDERS)
    return router, engine


class TestRouterBasic:
    def test_healthy_model_proceeds(self):
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="operational")
        )
        result = router.route("claude-opus-4-6", policy=CAREFUL)
        assert result.routed_to == "claude-opus-4-6"
        assert result.action == "proceed"

    def test_degraded_model_with_fast_policy_reroutes(self):
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="degraded_performance")
        )
        engine.update_status_signal(
            StatusPageSignal(provider="openai", status="operational")
        )
        result = router.route("claude-opus-4-6", policy=FAST)
        # FAST reroutes on degraded
        assert result.action == "rerouted"

    def test_degraded_model_with_careful_policy_warns(self):
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="degraded_performance")
        )
        result = router.route("claude-opus-4-6", policy=CAREFUL)
        assert result.action == "warned"
        assert result.routed_to == "claude-opus-4-6"

    def test_degraded_model_with_critical_policy_stops(self):
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="degraded_performance")
        )
        result = router.route("claude-opus-4-6", policy=CRITICAL)
        assert result.action == "stopped"

    def test_down_model_reroutes_to_alternative(self):
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="major_outage")
        )
        engine.update_status_signal(
            StatusPageSignal(provider="openai", status="operational")
        )

        policy = {
            "criticality": "medium",
            "on_degraded": "reroute",
            "on_down": "reroute",
            "acceptable_models": ["claude-opus-4-6", "gpt-4o"],
            "min_status": "healthy",
        }
        result = router.route("claude-opus-4-6", policy=policy)
        assert result.routed_to == "gpt-4o"
        assert result.action == "rerouted"

    def test_all_down_stops(self):
        router, engine = make_router_and_engine()
        engine.update_status_signal(
            StatusPageSignal(provider="anthropic", status="major_outage")
        )
        engine.update_status_signal(
            StatusPageSignal(provider="openai", status="major_outage")
        )

        policy = {
            "criticality": "high",
            "on_down": "reroute",
            "acceptable_models": ["claude-opus-4-6", "gpt-4o"],
            "min_status": "healthy",
        }
        result = router.route("claude-opus-4-6", policy=policy)
        assert result.action == "stopped"


class TestRouterMatchScoring:
    def test_same_tier_scores_higher(self):
        router, _ = make_router_and_engine()
        # gpt-4o is flagship like claude-opus — should score higher than sonnet (balanced)
        opus_to_gpt4o = router._match_score("claude-opus-4-6", "gpt-4o")
        opus_to_sonnet = router._match_score("claude-opus-4-6", "claude-sonnet-4-6")
        assert opus_to_gpt4o > opus_to_sonnet

    def test_unknown_model_neutral_score(self):
        router, _ = make_router_and_engine()
        score = router._match_score("claude-opus-4-6", "nonexistent")
        assert score == 0.5


class TestRoutingResult:
    def test_to_dict(self):
        result = RoutingResult(
            routed_to="gpt-4o",
            reason="test",
            action="rerouted",
        )
        d = result.to_dict()
        assert d["routed_to"] == "gpt-4o"
        assert d["action"] == "rerouted"
