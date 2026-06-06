"""
Provenance Stamper
══════════════════

Every piece of work gets a metadata stamp recording the conditions
under which it was created. Months later, when someone asks
"why was this output weird?", the stamp tells the story.

This is the honest record. For education — where grades matter and
fairness is non-negotiable — provenance is everything.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from llm_switchboard.config import defaults


logger = logging.getLogger("llm_switchboard.stamper")


# ── Confidence Flags ─────────────────────────────────────────────

class ConfidenceFlag(str, Enum):
    """How confident we are in the output given the conditions."""
    NOMINAL = "nominal"                     # Everything was healthy, output is trustworthy
    REVIEW_RECOMMENDED = "review_recommended"  # Something was off, human should check
    LOW_CONFIDENCE = "low_confidence"        # Significant issues, definitely review


# ── Provenance Stamp ─────────────────────────────────────────────

@dataclass
class ProvenanceStamp:
    """
    Immutable record of the conditions under which AI work was generated.

    Attach this to any output — a graded exam, a lesson plan, a report.
    It tells the full story of what happened.
    """
    stamp_id: str
    switchboard_version: str
    timestamp: str
    requested_model: str
    actual_model: str
    provider_status_at_call: dict[str, str]
    action: str                             # "proceed" | "rerouted" | "warned" | "stopped"
    reason: str
    confidence_flag: ConfidenceFlag
    health_snapshot_id: str                 # Links to stored health data
    metadata: dict = field(default_factory=dict)  # Caller can attach extra info

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "stamp_id": self.stamp_id,
            "switchboard_version": self.switchboard_version,
            "timestamp": self.timestamp,
            "requested_model": self.requested_model,
            "actual_model": self.actual_model,
            "provider_status_at_call": self.provider_status_at_call,
            "action": self.action,
            "reason": self.reason,
            "confidence_flag": self.confidence_flag.value,
            "health_snapshot_id": self.health_snapshot_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProvenanceStamp:
        """Deserialize from a dictionary."""
        return cls(
            stamp_id=data["stamp_id"],
            switchboard_version=data["switchboard_version"],
            timestamp=data["timestamp"],
            requested_model=data["requested_model"],
            actual_model=data["actual_model"],
            provider_status_at_call=data["provider_status_at_call"],
            action=data["action"],
            reason=data["reason"],
            confidence_flag=ConfidenceFlag(data["confidence_flag"]),
            health_snapshot_id=data["health_snapshot_id"],
            metadata=data.get("metadata", {}),
        )


# ── Stamper ──────────────────────────────────────────────────────

class Stamper:
    """
    Generates and stores provenance stamps.

    Every stamp is a self-contained record. The stamper also maintains
    an in-memory store for audit trail lookups (configurable to other
    backends in future versions).
    """

    VERSION = "1.0.1"

    def __init__(self, storage_enabled: bool = True):
        self._storage_enabled = storage_enabled
        self._stamps: dict[str, ProvenanceStamp] = {}  # stamp_id → stamp
        self._snapshots: dict[str, dict] = {}          # snapshot_id → health data

    def stamp(
        self,
        model_requested: str,
        model_used: str,
        action_taken: str,
        reason: str,
        provider_statuses: dict[str, str] | None = None,
        health_snapshot: dict | None = None,
        metadata: dict | None = None,
    ) -> ProvenanceStamp:
        """
        Generate a provenance stamp.

        Args:
            model_requested: What the caller asked for.
            model_used: What was actually used (may differ if rerouted).
            action_taken: What happened ("proceed", "rerouted", "warned", "stopped").
            reason: Human-readable explanation.
            provider_statuses: Optional dict of provider → status at call time.
            health_snapshot: Optional full health data to store.
            metadata: Optional extra info to attach.

        Returns:
            A ProvenanceStamp that should be attached to the output.
        """
        stamp_id = self._generate_id()
        snapshot_id = self._store_snapshot(health_snapshot) if health_snapshot else ""
        confidence = self._assess_confidence(model_requested, model_used, action_taken)

        stamp = ProvenanceStamp(
            stamp_id=stamp_id,
            switchboard_version=self.VERSION,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            requested_model=model_requested,
            actual_model=model_used,
            provider_status_at_call=provider_statuses or {},
            action=action_taken,
            reason=reason,
            confidence_flag=confidence,
            health_snapshot_id=snapshot_id,
            metadata=metadata or {},
        )

        if self._storage_enabled:
            self._stamps[stamp_id] = stamp

        logger.info(
            f"Stamp generated: {stamp_id} | "
            f"{model_requested}→{model_used} | "
            f"{action_taken} | {confidence.value}"
        )

        return stamp

    def get_stamp(self, stamp_id: str) -> ProvenanceStamp | None:
        """Retrieve a stored stamp by ID."""
        return self._stamps.get(stamp_id)

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        """Retrieve a stored health snapshot."""
        return self._snapshots.get(snapshot_id)

    def list_stamps(
        self,
        model: str | None = None,
        action: str | None = None,
        limit: int = 50,
    ) -> list[ProvenanceStamp]:
        """List stored stamps with optional filters."""
        stamps = list(self._stamps.values())

        if model:
            stamps = [
                s for s in stamps
                if s.requested_model == model or s.actual_model == model
            ]

        if action:
            stamps = [s for s in stamps if s.action == action]

        # Most recent first
        stamps.sort(key=lambda s: s.timestamp, reverse=True)
        return stamps[:limit]

    @property
    def stamp_count(self) -> int:
        return len(self._stamps)

    # ── Private Methods ──────────────────────────────────────────

    def _generate_id(self) -> str:
        """Generate a unique stamp ID."""
        return f"stamp_{uuid.uuid4().hex[:12]}"

    def _store_snapshot(self, snapshot: dict) -> str:
        """Store a health snapshot and return its ID."""
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        self._snapshots[snapshot_id] = {
            **snapshot,
            "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return snapshot_id

    def _assess_confidence(
        self,
        requested: str,
        used: str,
        action: str,
    ) -> ConfidenceFlag:
        """
        Determine confidence flag based on what happened.

        - proceed with primary healthy → nominal
        - rerouted to alternative → review recommended
        - warned / stopped → low confidence
        """
        if action == "proceed" and requested == used:
            return ConfidenceFlag.NOMINAL
        elif action == "rerouted":
            return ConfidenceFlag.REVIEW_RECOMMENDED
        elif action in ("warned", "stopped"):
            return ConfidenceFlag.LOW_CONFIDENCE
        else:
            return ConfidenceFlag.REVIEW_RECOMMENDED
