# LLM-Switchboard

**Proactive LLM health intelligence, routing, and provenance stamping.**

> *The operator who watches the lines and connects you to the right one.*

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## The Problem

Every AI application that calls LLM providers faces the same fragile reality:

- **Silent degradation** — A provider is technically "up" but responses are slow or lower quality. Your agent doesn't know.
- **Blind calls** — Your agent calls a model without checking if it's healthy. The call fails. Time and tokens wasted.
- **No provenance** — When you review AI-generated work from last Tuesday, you have no idea whether the model was healthy that day.
- **One-size-fits-all failure handling** — A retry might be fine for a chatbot. But for a student's graded exam? You need to stop and flag a human.

LLM gateways (Bifrost, LiteLLM, Portkey) handle failover and retries well. But they all work the same way: your request fails, *then* they react. **Switchboard checks before you call, decides based on what's at stake, and keeps an honest record of what happened.**

## Install

```bash
pip install llm-switchboard
```

## Quick Start

```python
from llm_switchboard import Switchboard

sb = Switchboard()

# 1. CHECK — Is the model healthy?
health = sb.check("claude-opus-4-6")
print(health["status"])        # "healthy" | "degraded" | "down"
print(health["recommendation"])  # "proceed" | "caution" | "reroute"

# 2. ROUTE — What should I do?
result = sb.route(
    preferred_model="claude-opus-4-6",
    policy="careful",  # or "fast", "critical", or a custom dict
)
print(result.routed_to)  # The model to actually use
print(result.action)     # "proceed" | "rerouted" | "warned" | "stopped"

# 3. STAMP — Record what happened
stamp = sb.stamp(
    model_requested="claude-opus-4-6",
    model_used=result.routed_to,
    action_taken=result.action,
    reason=result.reason,
)
# Attach this stamp to your output for audit trail
```

## Three Built-in Policies

| Policy | On Degraded | On Down | Best For |
|--------|------------|---------|----------|
| **FAST** | Reroute silently | Reroute silently | Chatbots, summaries |
| **CAREFUL** | Warn, proceed | Reroute with warning | Content generation, lesson plans |
| **CRITICAL** | Stop + alert human | Stop + alert human | Grading, legal, medical, financial |

```python
from llm_switchboard.policies import FAST, CAREFUL, CRITICAL

# Or use a custom policy
result = sb.route("claude-opus-4-6", policy={
    "criticality": "high",
    "on_degraded": "reroute",
    "on_down": "stop",
    "acceptable_models": ["claude-opus-4-6", "gpt-4o"],
})
```

## Provenance Stamps

Every routing decision produces a stamp you can attach to your output:

```python
{
    "stamp_id": "stamp_abc123def456",
    "requested_model": "claude-opus-4-6",
    "actual_model": "gpt-4o",
    "action": "rerouted",
    "reason": "Primary model degraded during Anthropic minor outage",
    "confidence_flag": "review_recommended",
    "provider_status_at_call": {
        "anthropic": "minor_outage",
        "openai": "operational"
    }
}
```

Months later, when someone asks "why was this output weird?", the stamp tells the story.

## REST API

Run Switchboard as a service for non-Python applications:

```bash
switchboard serve --port 8080
```

```bash
# Check a model
curl http://localhost:8080/health/claude-opus-4-6

# Route with a policy
curl -X POST http://localhost:8080/route \
  -H "Content-Type: application/json" \
  -d '{"preferred_model": "claude-opus-4-6", "policy": "careful"}'
```

## CLI

```bash
switchboard check claude-opus-4-6    # Health check
switchboard status                   # All providers
switchboard route -m claude-opus-4-6 -p careful  # Route
switchboard providers                # List all
switchboard serve --port 8080        # REST API
```

## Supported Providers

Anthropic, OpenAI, Google (Gemini), Mistral, xAI, Cohere, Groq, Together AI, AWS Bedrock.

Adding a provider requires implementing one class with three methods. See [docs/providers.md](docs/providers.md).

## What Makes This Different

Switchboard is **advisory, not invasive**. It doesn't sit in your request path. It doesn't add latency. It doesn't require you to change your API calls. You ask it "what's the state of the world?" and it tells you.

This means you can use Switchboard *with* Bifrost, *with* LiteLLM, *with* Portkey, or with plain API calls. It's the intelligence layer that any routing system can consume.

| Capability | Gateways | LLM-Switchboard |
|------------|----------|-----------------|
| Retry failed requests | ✓ | Not a proxy |
| Health detection | From observed errors | From external signals *before* errors |
| Status page monitoring | ✗ | ✓ |
| Provenance stamping | ✗ | ✓ |
| Task-criticality policies | ✗ | ✓ |
| Model equivalence scoring | Basic | Capability-aware |
| Works standalone | Requires traffic routing | Advisory — zero latency overhead |

## Built By

[Xmmersia](https://github.com/Ayahualulco) — an education platform where AI agents tutor, grade, and create learning materials. We built Switchboard because our students deserve reliable AI. We're sharing it because every team running AI agents in production faces this same gap.

*Switchboard watches so our agents can teach. It routes so learning never stops. And it stamps so we always know the truth about what happened.*

## License

MIT

> **Note:** This project is unrelated to the VS Code extension "LLM Switchboard" for local offline model chat. This is a production routing and provenance library for AI agents.
