"""
LLM-Switchboard Models
══════════════════════

Model catalog, capability matching, and equivalence scoring.
"""

from llm_switchboard.models.registry import ModelInfo, ModelRegistry
from llm_switchboard.models.equivalence import equivalence_score, rank_alternatives

__all__ = [
    "ModelInfo",
    "ModelRegistry",
    "equivalence_score",
    "rank_alternatives",
]
