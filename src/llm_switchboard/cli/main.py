"""
LLM-Switchboard CLI
═══════════════════

Command-line interface for health checks, routing, and status.

    switchboard check claude-opus-4-6
    switchboard status
    switchboard route --model claude-opus-4-6 --policy careful
    switchboard serve --port 8080
    switchboard providers
"""

from __future__ import annotations

import json
import sys

import click


@click.group()
@click.version_option(version="1.0.0", prog_name="llm-switchboard")
def cli():
    """LLM-Switchboard — Proactive LLM health intelligence."""
    pass


@cli.command()
@click.argument("model")
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON")
def check(model: str, json_output: bool):
    """Check health of a specific model."""
    from llm_switchboard import Switchboard

    sb = Switchboard()
    result = sb.check(model)

    if json_output:
        click.echo(json.dumps(result, indent=2))
        return

    # Pretty output
    status = result["status"]
    colors = {"healthy": "green", "degraded": "yellow", "down": "red", "unknown": "white"}
    color = colors.get(status, "white")

    click.echo()
    click.secho(f"  Model:          {result['model']}", bold=True)
    click.secho(f"  Provider:       {result['provider']}")
    click.secho(f"  Status:         {status}", fg=color, bold=True)
    click.secho(f"  Confidence:     {result['confidence']:.0%}")
    click.secho(f"  Recommendation: {result['recommendation']}")
    click.secho(f"  Status Page:    {result['status_page']}")

    if result.get("latency_ms"):
        click.secho(f"  Latency:        {result['latency_ms']:.0f}ms")

    if result.get("alternatives"):
        click.echo()
        click.secho("  Alternatives:", bold=True)
        for alt in result["alternatives"]:
            alt_color = colors.get(alt["status"], "white")
            click.secho(
                f"    {alt['model']:30s} "
                f"status={alt['status']:8s} "
                f"match={alt['match_score']:.2f}",
                fg=alt_color,
            )

    click.echo()


@cli.command()
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON")
def status(json_output: bool):
    """Check health of all providers."""
    from llm_switchboard import Switchboard

    sb = Switchboard()
    info = sb.status()

    if json_output:
        click.echo(json.dumps(info, indent=2))
        return

    click.echo()
    click.secho(f"  LLM-Switchboard v{info['switchboard_version']}", bold=True)
    click.secho(f"  Providers: {info['providers']}  |  Models: {info['models']}  |  Stamps: {info['stamps_stored']}")
    click.echo()

    summary = info["health_summary"]
    click.secho(f"  Healthy:  {summary.get('healthy', 0)}", fg="green")
    click.secho(f"  Degraded: {summary.get('degraded', 0)}", fg="yellow")
    click.secho(f"  Down:     {summary.get('down', 0)}", fg="red")
    click.secho(f"  Unknown:  {summary.get('unknown', 0)}")
    click.echo()


@cli.command()
@click.option("--model", "-m", default="claude-opus-4-6", help="Preferred model")
@click.option("--policy", "-p", default="careful", help="Policy: fast, careful, critical")
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON")
def route(model: str, policy: str, json_output: bool):
    """Route a request with a policy."""
    from llm_switchboard import Switchboard

    sb = Switchboard()
    result = sb.route(preferred_model=model, policy=policy)

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    colors = {
        "proceed": "green",
        "rerouted": "yellow",
        "warned": "yellow",
        "stopped": "red",
    }
    color = colors.get(result.action, "white")

    click.echo()
    click.secho(f"  Routed to: {result.routed_to}", bold=True, fg=color)
    click.secho(f"  Action:    {result.action}", fg=color)
    click.secho(f"  Reason:    {result.reason}")

    if result.provenance:
        flag = result.provenance.get("confidence_flag", "unknown")
        flag_colors = {
            "nominal": "green",
            "review_recommended": "yellow",
            "low_confidence": "red",
        }
        click.secho(f"  Confidence: {flag}", fg=flag_colors.get(flag, "white"))
        click.secho(f"  Stamp ID:   {result.provenance.get('stamp_id', 'n/a')}")

    click.echo()


@cli.command()
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON")
def providers(json_output: bool):
    """List all supported providers and models."""
    from llm_switchboard import Switchboard

    sb = Switchboard()
    provider_list = sb.list_providers()

    if json_output:
        all_models = sb.list_models()
        click.echo(json.dumps({"providers": provider_list, "models": all_models}, indent=2))
        return

    click.echo()
    for provider in provider_list:
        click.secho(f"  {provider}", bold=True)
        models = sb.list_models(provider=provider)
        for m in models:
            caps = ", ".join(m.get("capabilities", [])[:4])
            click.echo(f"    {m['id']:40s} [{m['tier']}] {caps}")
        click.echo()


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8080, type=int, help="Port to listen on")
def serve(host: str, port: int):
    """Run Switchboard as a REST API server."""
    from llm_switchboard.api.server import serve as run_server

    click.secho(f"  Starting Switchboard API on {host}:{port}", bold=True)
    run_server(host=host, port=port)


@cli.command()
@click.argument("key")
@click.argument("value")
def config(key: str, value: str):
    """Set a configuration value (e.g., switchboard config anthropic.api_key sk-...)."""
    # For v1.0, just acknowledge — actual config storage is future work
    click.secho(f"  Config set: {key} = {'*' * len(value)}", fg="green")
    click.echo("  (Note: Config persistence coming in v1.1. Use environment variables for now.)")


if __name__ == "__main__":
    cli()
