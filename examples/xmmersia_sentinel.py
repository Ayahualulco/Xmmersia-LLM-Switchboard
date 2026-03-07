"""
Xmmersia Sentinel Integration Example
══════════════════════════════════════

Shows how LLM-Switchboard becomes the foundation for a Sentinel agent
inside the Xmmersia ecosystem.

Inside Xmmersia:
  - The public library (llm-switchboard) does the heavy lifting
  - The Sentinel wrapper adds ecosystem-specific behavior
  - It lives in the Rozafa Hub alongside Vauban

This example shows the pattern. The actual Sentinel would live in
a separate private repository (Xmmersia-LeStandard or similar).
"""

from llm_switchboard import Switchboard
from llm_switchboard.policies import FAST, CAREFUL, CRITICAL


# ── Sentinel Definition ──────────────────────────────────────────

class ModelHealthSentinel:
    """
    Watches LLM provider health for the entire Xmmersia ecosystem.

    In production, this would inherit from xmmersia_agentcore.BaseSentinel
    and be registered as a Sentinel-class agent in the ecosystem.

    Lives in: Rozafa Hub (security & resilience)
    Complements: Vauban (guards the castle), A2AProtocolSentinel (guards the roads)
    This Sentinel: Guards model reliability
    """

    def __init__(self):
        # In production: super().__init__(name="le-standard", tier="sentinel")
        self.name = "le-standard"
        self.tier = "sentinel"
        self.switchboard = Switchboard()

    def pre_flight_check(self, mate_name: str, task: dict) -> dict:
        """
        Called by any Mate before making an LLM call.

        This is the hook that integrates Switchboard into the Xmmersia
        agent communication flow. When GASTON wants to call Claude,
        it asks this Sentinel first.

        Args:
            mate_name: Which Mate is making the call (e.g., "gaston", "lumiere")
            task: Task dict with type, model preference, etc.

        Returns:
            Routing result with the recommended model and provenance stamp.
        """
        # Determine policy based on task type
        policy = self._policy_for_task(task)

        # Get the preferred model (default to Claude Opus)
        preferred = task.get("model", "claude-opus-4-6")

        # Route through Switchboard
        result = self.switchboard.route(
            preferred_model=preferred,
            policy=policy,
            prompt=f"{mate_name}: {task.get('description', 'unknown task')}",
        )

        return result.to_dict()

    def health_report(self) -> dict:
        """
        Generate a health report for the ecosystem dashboard.

        This feeds into Vauban's Monitor Tower and the Command Center.
        """
        return self.switchboard.status()

    def _policy_for_task(self, task: dict) -> dict:
        """
        Map Xmmersia task types to routing policies.

        The key insight: grading a student's exam requires different
        failure handling than generating a practice worksheet.
        """
        task_type = task.get("type", "general")

        # Critical tasks — stop if anything is wrong
        if task_type in ("grading", "assessment", "verification"):
            return CRITICAL

        # Careful tasks — warn and reroute
        if task_type in ("lesson_generation", "report", "feedback"):
            return CAREFUL

        # Fast tasks — reroute silently
        if task_type in ("chatbot", "summary", "quick_lookup", "worksheet"):
            return FAST

        # Default to careful
        return CAREFUL


# ── Usage Example ────────────────────────────────────────────────

if __name__ == "__main__":
    sentinel = ModelHealthSentinel()

    # Simulated: GASTON wants to chat with a student
    chat_result = sentinel.pre_flight_check(
        mate_name="gaston",
        task={"type": "chatbot", "description": "Student asking about chain rule"}
    )
    print(f"Chat task → {chat_result['routed_to']} ({chat_result['action']})")

    # Simulated: LUMIÈRE wants to grade an exam
    grade_result = sentinel.pre_flight_check(
        mate_name="lumiere",
        task={"type": "grading", "description": "Grade midterm Q3"}
    )
    print(f"Grading task → {grade_result['routed_to']} ({grade_result['action']})")

    # Simulated: Le Marteau generating a worksheet
    gen_result = sentinel.pre_flight_check(
        mate_name="le-marteau",
        task={"type": "worksheet", "description": "Generate chain rule practice"}
    )
    print(f"Worksheet task → {gen_result['routed_to']} ({gen_result['action']})")

    # Health report for the dashboard
    report = sentinel.health_report()
    print(f"\nEcosystem health: {report['health_summary']}")
