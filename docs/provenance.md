# Provenance Stamp Specification

Every piece of work generated through Switchboard gets a metadata stamp recording the conditions under which it was created. This is the honest record.

## Stamp Format

```json
{
    "stamp_id": "stamp_abc123def456",
    "switchboard_version": "1.0.0",
    "timestamp": "2026-03-07T14:32:15Z",
    "requested_model": "claude-opus-4-6",
    "actual_model": "gpt-4o",
    "provider_status_at_call": {
        "anthropic": "minor_outage",
        "openai": "operational"
    },
    "action": "rerouted",
    "reason": "Primary model degraded during Anthropic minor outage",
    "confidence_flag": "review_recommended",
    "health_snapshot_id": "snap_abc123",
    "trust_tier_at_call": "trusted",
    "metadata": {}
}
```

## Fields

### stamp_id
Unique identifier for this stamp. Format: `stamp_{12 hex chars}`.

### switchboard_version
Version of Switchboard that generated this stamp.

### timestamp
ISO 8601 UTC timestamp of when the stamp was generated.

### requested_model / actual_model
What the caller asked for vs. what was actually used. If these differ, the request was rerouted.

### provider_status_at_call
Snapshot of every provider's status at the moment the stamp was generated. This is the key provenance data — it records the state of the world.

### action
What happened: `proceed`, `rerouted`, `warned`, or `stopped`.

### reason
Human-readable explanation of why this action was taken.

### confidence_flag
How much trust to place in the output:

- **nominal**: Everything was healthy. Output is trustworthy.
- **review_recommended**: Something was off (rerouted, degraded provider). A human should review.
- **low_confidence**: Significant issues. The output may be unreliable.

### health_snapshot_id
Links to a stored health snapshot with detailed signal data. Use `GET /stamp/{stamp_id}` to retrieve.

### trust_tier_at_call
Trust tier of the model **actually used** — `trusted`, `watched`, or `untrusted`. On a reroute this describes the substitute, not the model originally requested, since the substitute is what produced the output.

Health records whether the model was *up*; this records whether it was *proven*. Reviewing a graded exam months later, both matter: a `watched` tier on a high-stakes output is a flag even when every provider was operational. See [policies.md](policies.md) for which tiers each policy admits.

Defaults to `trusted` when a stamp is generated outside routing, and when reading older stamps written before this field existed.

### metadata
Caller-defined extra data. Attach anything relevant: student ID, task type, course section, etc.

## Confidence Flag Logic

| Condition | Flag |
|-----------|------|
| Primary model used, healthy | nominal |
| Rerouted to alternative | review_recommended |
| Proceeded with warning | review_recommended |
| Stopped (no generation) | low_confidence |

## Usage in Xmmersia

In the Xmmersia ecosystem, every graded exam, lesson plan, and assessment report gets a provenance stamp. This enables:

- **Audit trails**: When reviewing a grade months later, the stamp shows whether the model was healthy.
- **FERPA compliance**: Transparent AI decision-making for student records.
- **Quality control**: Flag outputs generated under degraded conditions for human review.
