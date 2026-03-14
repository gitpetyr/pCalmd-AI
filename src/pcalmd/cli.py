"""Click CLI for pCalmd-AI."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pcalmd.config import Settings, load_settings
from pcalmd.output.writer import OutputWriter
from pcalmd.pipeline import Pipeline

console = Console()


@click.group()
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to config.toml.",
)
@click.pass_context
def main(ctx: click.Context, config_path: Path | None) -> None:
    """pCalmd-AI: AI-assisted JavaScript deobfuscation tool."""
    ctx.ensure_object(dict)
    ctx.obj["settings"] = load_settings(config_path)


# -----------------------------------------------------------------------
# deobfuscate
# -----------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("-p", "--provider", default=None, help="AI provider (anthropic/openai/gemini/custom).")
@click.option("-m", "--model", default=None, help="Model name.")
@click.option("--api-base", default=None, help="Custom API base URL.")
@click.option("--no-simplify", is_flag=True, help="Skip simplification.")
@click.option("--no-rename", is_flag=True, help="Skip variable renaming.")
@click.option("--no-comment", is_flag=True, help="Skip comment insertion.")
@click.option("--explain", is_flag=True, help="Enable code explanation.")
@click.option("--no-verify", is_flag=True, help="Skip AST verification.")
@click.option("--dry-run", is_flag=True, help="Show chunking plan without AI calls.")
@click.option("--format", "fmt", type=click.Choice(["file", "stdout", "diff"]), default=None)
@click.pass_context
def deobfuscate(
    ctx: click.Context,
    input_file: Path,
    output_path: Path | None,
    provider: str | None,
    model: str | None,
    api_base: str | None,
    no_simplify: bool,
    no_rename: bool,
    no_comment: bool,
    explain: bool,
    no_verify: bool,
    dry_run: bool,
    fmt: str | None,
) -> None:
    """Deobfuscate a JavaScript file."""
    settings: Settings = ctx.obj["settings"]

    # CLI overrides.
    if provider:
        settings.ai.provider = provider
    if model:
        settings.ai.model = model
    if api_base:
        settings.ai.api_base = api_base
    if no_simplify:
        settings.pipeline.simplify = False
    if no_rename:
        settings.pipeline.rename = False
    if no_comment:
        settings.pipeline.comment = False
    if explain:
        settings.pipeline.explain = True
    if no_verify:
        settings.pipeline.verify = False
    if fmt:
        settings.output.format = fmt

    source = input_file.read_text(encoding="utf-8")
    pipeline = Pipeline(settings)

    if dry_run:
        _show_dry_run(pipeline, source, input_file)
        return

    # Check API key.
    if not settings.ai.api_key:
        _check_env_api_key(settings.ai.provider)

    result = asyncio.run(pipeline.deobfuscate(source))

    # Warnings.
    for w in result.warnings:
        console.print(f"[yellow]WARNING:[/yellow] {w}")

    # Write output.
    writer = OutputWriter(fmt=settings.output.format, suffix=settings.output.suffix)
    out = writer.write(result.code, input_file, output_path, original=source)

    # Summary.
    console.print(
        f"\n[green]Done.[/green] "
        f"{result.chunks_processed} chunks processed, "
        f"{result.chunks_failed} failed."
    )
    if out:
        console.print(f"Output: {out}")

    if result.explanations:
        console.print("\n[bold]Explanations:[/bold]")
        for exp in result.explanations:
            console.print(exp)


# -----------------------------------------------------------------------
# analyze
# -----------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def analyze(ctx: click.Context, input_file: Path) -> None:
    """Analyze JavaScript file structure (no AI calls)."""
    settings: Settings = ctx.obj["settings"]
    source = input_file.read_text(encoding="utf-8")
    pipeline = Pipeline(settings)
    result = pipeline.analyze(source)

    console.print(f"\n[bold]File:[/bold] {input_file}")
    console.print(f"Lines: {result.total_lines}  Bytes: {result.total_bytes}")
    console.print(f"Top-level units: {result.units}  Chunks: {result.chunks}")

    if result.imports:
        console.print(f"\n[bold]Imports ({len(result.imports)}):[/bold]")
        for imp in result.imports:
            console.print(f"  {imp}")

    if result.function_signatures:
        console.print(
            f"\n[bold]Function signatures ({len(result.function_signatures)}):[/bold]"
        )
        for sig in result.function_signatures:
            console.print(f"  {sig}")

    if result.chunk_details:
        console.print(f"\n[bold]Chunk plan:[/bold]")
        table = Table(show_header=True)
        table.add_column("#", justify="right", width=4)
        table.add_column("Units", justify="right", width=6)
        table.add_column("Tokens", justify="right", width=8)
        table.add_column("Oversized", width=10)
        table.add_column("Names")

        for cd in result.chunk_details:
            table.add_row(
                str(cd["index"]),
                str(cd["units"]),
                str(cd["tokens_est"]),
                "YES" if cd["oversized"] else "",
                ", ".join(cd["unit_names"]) if cd["unit_names"] else "-",  # type: ignore[arg-type]
            )
        console.print(table)


# -----------------------------------------------------------------------
# init-config
# -----------------------------------------------------------------------


@main.command("init-config")
def init_config() -> None:
    """Generate a config.example.toml in the current directory."""
    target = Path("config.toml")
    if target.exists():
        console.print(f"[yellow]{target} already exists, skipping.[/yellow]")
        return

    example = Path(__file__).parent.parent.parent / "config.example.toml"
    if example.is_file():
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        target.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    console.print(f"[green]Created {target}[/green]")


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _show_dry_run(pipeline: Pipeline, source: str, path: Path) -> None:
    result = pipeline.analyze(source)
    console.print(f"\n[bold]Dry-run for:[/bold] {path}")
    console.print(f"Units: {result.units}, Chunks: {result.chunks}")
    for cd in result.chunk_details:
        names = ", ".join(cd["unit_names"]) if cd["unit_names"] else "-"  # type: ignore[arg-type]
        flag = " [OVERSIZED]" if cd["oversized"] else ""
        console.print(
            f"  Chunk {cd['index']}: {cd['units']} units, "
            f"~{cd['tokens_est']} tokens{flag} ({names})"
        )


def _check_env_api_key(provider: str) -> None:
    """Warn if no API key is configured."""
    import os

    env_keys = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_key = env_keys.get(provider)
    if env_key and not os.environ.get(env_key) and not os.environ.get("PCALMD_AI__API_KEY"):
        console.print(
            f"[red]No API key found.[/red] Set {env_key} or PCALMD_AI__API_KEY "
            f"or add api_key to config.toml."
        )
        sys.exit(1)


_DEFAULT_CONFIG = """\
[ai]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
api_key = ""
# api_base = "http://localhost:8080/v1"  # only for custom provider
temperature = 0.2
max_tokens = 8192

[chunking]
max_tokens = 3000
context_tokens = 1000

[pipeline]
simplify = true
rename = true
comment = true
explain = false
verify = true
max_retries = 2

[rate_limit]
max_concurrent = 3
requests_per_minute = 50

[output]
format = "file"
suffix = ".deobfuscated"
"""
