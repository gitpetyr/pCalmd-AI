"""Configuration loading for pCalmd-AI.

Config priority (highest to lowest):
    1. CLI parameters (applied by caller after loading)
    2. Environment variables (PCALMD_ prefix, nested with __)
    3. config.toml file
    4. Defaults defined in model classes
"""

from __future__ import annotations

from pathlib import Path

import tomllib

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseModel):
    """AI provider and model configuration."""

    provider: str = "anthropic"  # anthropic / openai / gemini / custom
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    api_base: str | None = None  # only for custom provider
    temperature: float = 0.2
    max_tokens: int = 8192


class ChunkingSettings(BaseModel):
    """Source-code chunking parameters."""

    max_tokens: int = 3000
    context_tokens: int = 1000


class PipelineSettings(BaseModel):
    """Deobfuscation pipeline stage toggles."""

    simplify: bool = True
    rename: bool = True
    comment: bool = True
    explain: bool = False
    verify: bool = True
    max_retries: int = 2


class RateLimitSettings(BaseModel):
    """Rate-limiting for API requests."""

    max_concurrent: int = 3
    requests_per_minute: int = 50


class OutputSettings(BaseModel):
    """Output format and naming."""

    format: str = "file"  # file / stdout / diff
    suffix: str = ".deobfuscated"


class Settings(BaseSettings):
    """Root settings for pCalmd-AI.

    Composes all sub-setting groups and supports loading from
    environment variables (PCALMD_ prefix) and TOML config files.
    """

    model_config = SettingsConfigDict(
        env_prefix="PCALMD_",
        env_nested_delimiter="__",
    )

    ai: AISettings = AISettings()
    chunking: ChunkingSettings = ChunkingSettings()
    pipeline: PipelineSettings = PipelineSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    output: OutputSettings = OutputSettings()


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings with the standard priority chain.

    Resolution order (highest wins):
        1. CLI params  -- applied by the caller after this returns
        2. Env vars    -- PCALMD_ prefix, e.g. PCALMD_AI__API_KEY
        3. TOML file   -- *config_path*, then ``./config.toml``
        4. Defaults    -- values declared on the model fields

    Parameters
    ----------
    config_path:
        Explicit path to a TOML config file.  When *None* the loader
        falls back to ``./config.toml`` if it exists, otherwise pure
        defaults (+ env vars) are used.

    Returns
    -------
    Settings
        Fully resolved configuration object.
    """
    toml_path = config_path
    if toml_path is None:
        default_path = Path("config.toml")
        if default_path.is_file():
            toml_path = default_path

    if toml_path is not None and toml_path.is_file():
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        return Settings(**data)

    return Settings()
