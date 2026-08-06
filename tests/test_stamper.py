"""
Tests for Provenance Stamper
════════════════════════════
"""

import pytest

from llm_switchboard.core.stamper import ConfidenceFlag, ProvenanceStamp, Stamper


class TestStamper:
    def test_basic_stamp_generation(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="claude-opus-4-6",
            action_taken="proceed",
            reason="Primary model is healthy",
        )
        assert stamp.stamp_id.startswith("stamp_")
        assert stamp.requested_model == "claude-opus-4-6"
        assert stamp.actual_model == "claude-opus-4-6"
        assert stamp.action == "proceed"
        assert stamp.confidence_flag == ConfidenceFlag.NOMINAL

    def test_rerouted_stamp_confidence(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="gpt-4o",
            action_taken="rerouted",
            reason="Primary model degraded",
        )
        assert stamp.confidence_flag == ConfidenceFlag.REVIEW_RECOMMENDED

    def test_stopped_stamp_confidence(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="claude-opus-4-6",
            action_taken="stopped",
            reason="Primary model down; stopped per policy",
        )
        assert stamp.confidence_flag == ConfidenceFlag.LOW_CONFIDENCE

    def test_stamp_storage_and_retrieval(self):
        stamper = Stamper(storage_enabled=True)
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="gpt-4o",
            action_taken="rerouted",
            reason="test",
        )
        # Retrieve by ID
        retrieved = stamper.get_stamp(stamp.stamp_id)
        assert retrieved is not None
        assert retrieved.stamp_id == stamp.stamp_id

    def test_stamp_not_found(self):
        stamper = Stamper()
        assert stamper.get_stamp("nonexistent") is None

    def test_stamp_to_dict(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="claude-opus-4-6",
            action_taken="proceed",
            reason="healthy",
        )
        d = stamp.to_dict()
        assert d["requested_model"] == "claude-opus-4-6"
        assert d["confidence_flag"] == "nominal"
        assert "stamp_id" in d
        assert "timestamp" in d

    def test_stamp_from_dict_roundtrip(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="gpt-4o",
            action_taken="rerouted",
            reason="test roundtrip",
            provider_statuses={"anthropic": "degraded", "openai": "operational"},
        )
        d = stamp.to_dict()
        restored = ProvenanceStamp.from_dict(d)
        assert restored.stamp_id == stamp.stamp_id
        assert restored.confidence_flag == stamp.confidence_flag
        assert restored.provider_status_at_call == stamp.provider_status_at_call

    def test_list_stamps(self):
        stamper = Stamper()
        for i in range(5):
            stamper.stamp(
                model_requested="claude-opus-4-6",
                model_used="claude-opus-4-6",
                action_taken="proceed" if i % 2 == 0 else "rerouted",
                reason=f"test {i}",
            )
        assert stamper.stamp_count == 5

        # Filter by action
        rerouted = stamper.list_stamps(action="rerouted")
        assert len(rerouted) == 2

    def test_metadata_attachment(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="claude-opus-4-6",
            action_taken="proceed",
            reason="test",
            metadata={"student_id": "abc123", "task": "midterm_q3"},
        )
        assert stamp.metadata["student_id"] == "abc123"
        assert stamp.metadata["task"] == "midterm_q3"

    def test_trust_tier_at_call_defaults_to_trusted(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="claude-opus-4-6",
            action_taken="proceed",
            reason="Primary model is healthy",
        )
        assert stamp.trust_tier_at_call == "trusted"

    def test_trust_tier_at_call_recorded_and_round_trips(self):
        stamper = Stamper()
        stamp = stamper.stamp(
            model_requested="grok-build-0.1",
            model_used="grok-build-0.1",
            action_taken="proceed",
            reason="test",
            trust_tier_at_call="watched",
        )
        assert stamp.trust_tier_at_call == "watched"
        d = stamp.to_dict()
        assert d["trust_tier_at_call"] == "watched"
        restored = ProvenanceStamp.from_dict(d)
        assert restored.trust_tier_at_call == "watched"

    def test_storage_disabled(self):
        stamper = Stamper(storage_enabled=False)
        stamp = stamper.stamp(
            model_requested="claude-opus-4-6",
            model_used="claude-opus-4-6",
            action_taken="proceed",
            reason="test",
        )
        # Stamp is generated but not stored
        assert stamper.get_stamp(stamp.stamp_id) is None
        assert stamper.stamp_count == 0
