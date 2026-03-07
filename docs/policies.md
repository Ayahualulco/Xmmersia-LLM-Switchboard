# Policy Configuration Guide

Policies control how Switchboard handles model degradation. The key insight: **different tasks have different stakes.**

## Built-in Policies

### FAST
Maximize availability. Reroute silently, never block.

| Provider Status | Action |
|----------------|--------|
| Healthy | Proceed |
| Degraded | Reroute silently |
| Down | Reroute silently |
| All down | Proceed with warning |

Best for: chatbots, summaries, quick lookups.

### CAREFUL
Balance quality and availability. Warn when degraded, reroute when down.

| Provider Status | Action |
|----------------|--------|
| Healthy | Proceed |
| Degraded | Proceed with warning |
| Down | Reroute with warning |
| All down | Stop and queue |

Best for: content generation, lesson plans, code writing.

### CRITICAL
Never compromise. Stop and alert a human if anything is wrong.

| Provider Status | Action |
|----------------|--------|
| Healthy | Proceed |
| Degraded | Stop and alert |
| Down | Stop and alert |
| All down | Stop and alert |

Best for: grading, legal documents, medical information, financial analysis.

## Custom Policies

```python
policy = {
    "priority": "quality",           # quality | speed | cost
    "criticality": "high",           # low | medium | high | critical
    "on_degraded": "reroute",        # proceed | warn | reroute | stop
    "on_down": "stop",               # reroute | stop | queue
    "acceptable_models": [           # fallback preference order
        "claude-opus-4-6",
        "gpt-4o",
    ],
    "min_status": "healthy",         # healthy | degraded
    "max_latency_ms": 5000,          # optional latency ceiling
    "notify": "webhook:https://...", # optional notification target
}
```

## Policy Fields

- **priority**: What matters most — quality of output, speed of response, or cost.
- **criticality**: How important is this task? Affects logging and notification behavior.
- **on_degraded**: What to do when the primary model is degraded but not down.
- **on_down**: What to do when the primary model is completely down.
- **acceptable_models**: Ordered list of fallback models. Empty means try all known models.
- **min_status**: Minimum health status to accept for a fallback model.
- **max_latency_ms**: Maximum acceptable latency. Models exceeding this are skipped.
- **notify**: Webhook URL or notification target for stop/reroute events.
