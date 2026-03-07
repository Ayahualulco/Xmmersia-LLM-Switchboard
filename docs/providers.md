# Adding New Providers

LLM-Switchboard is designed to make adding new providers simple. Each provider is a single Python file that implements three methods.

## Steps

### 1. Create the adapter file

Create `src/llm_switchboard/providers/yourprovider.py`:

```python
from llm_switchboard.core.health_engine import StatusPageSignal, ProbeSignal
from llm_switchboard.providers.base import BaseProvider

class YourProvider(BaseProvider):
    async def fetch_status(self) -> StatusPageSignal:
        """Fetch current status from the provider's status page."""
        url = self.config.status_api_url
        if not url:
            return StatusPageSignal(provider="yourprovider", status="unknown")
        
        data = await self._fetch_statuspage_json(url)
        if not data:
            return StatusPageSignal(provider="yourprovider", status="unknown")
        
        status = self._parse_statuspage_indicator(data)
        return StatusPageSignal(provider="yourprovider", status=status, raw_data=data)

    def list_models(self) -> list[dict]:
        return self.config.models
    
    async def probe(self, model: str) -> ProbeSignal | None:
        """Optional: send a test request. Requires API key."""
        if not self._api_key:
            return None
        # Implement lightweight test request here
        ...
```

### 2. Add to providers.yaml

Add the provider's configuration:

```yaml
yourprovider:
  name: YourProvider
  status_page_url: "https://status.yourprovider.com"
  status_api_url: "https://status.yourprovider.com/api/v2/summary.json"
  api_base_url: "https://api.yourprovider.com"
  api_key_env: "YOURPROVIDER_API_KEY"
  models:
    - id: "your-model-v1"
      name: "Your Model v1"
      capabilities: [reasoning, coding, analysis]
      tier: flagship
      context_window: 128000
```

### 3. Register in the provider registry

Add to `providers/__init__.py`:

```python
from llm_switchboard.providers.yourprovider import YourProvider

PROVIDER_REGISTRY["yourprovider"] = YourProvider
```

### 4. Add tests

Create `tests/test_providers/test_yourprovider.py` with tests for status parsing and model listing.

## Status Page Formats

Most major providers use **Atlassian Statuspage**, which exposes a JSON API at `/api/v2/summary.json`. The `BaseProvider` class includes helpers for parsing this format. If a provider uses a different format, implement custom parsing in your `fetch_status()` method.

## Probing

Active probing is optional but recommended for catching silent degradation. It sends a minimal test prompt and measures latency. Keep probes cheap (max 5 output tokens).

## Signal Sources Per Provider

Transparency matters — here's exactly what Switchboard checks for each provider.

| Provider | Status Page | Format | Probe Endpoint | Notes |
|----------|-------------|--------|----------------|-------|
| **Anthropic** | status.anthropic.com/api/v2/summary.json | Atlassian Statuspage | `/v1/messages` | Full probe + status page |
| **OpenAI** | status.openai.com/api/v2/summary.json | Atlassian Statuspage | `/v1/chat/completions` | Full probe + status page |
| **Google** | status.cloud.google.com/summary.json | Google Cloud format | `/v1beta/models/{model}:generateContent` | Probe via Gemini API |
| **Mistral** | status.mistral.ai/api/v2/summary.json | Atlassian Statuspage | — | Status page only (v1.0) |
| **xAI** | status.x.ai | Custom (live monitoring) | `/v1/chat/completions` | OpenAI-compatible API; status page is custom format (not Atlassian), so we check reachability + parse when possible |
| **Cohere** | status.cohere.com/api/v2/summary.json | Atlassian Statuspage | — | Status page only (v1.0) |
| **Groq** | status.groq.com/api/v2/summary.json | Atlassian Statuspage | — | Status page only (v1.0) |
| **Together** | status.together.ai/api/v2/summary.json | Atlassian Statuspage | — | Status page only (v1.0) |
| **Bedrock** | health.aws.amazon.com | AWS Health Dashboard | — | Not yet implemented (requires boto3) |

### Fallback behavior

When an API key is not configured for a provider, probing is skipped and Switchboard relies solely on status page signals. When a status page is unreachable or uses an unknown format, the provider's status is reported as `"unknown"` with reduced confidence. This is by design — Switchboard is honest about what it knows and what it doesn't.
