"""AI module -- LiteLLM provider wrapper, prompt templates, and rate limiter."""

from pcalmd.ai.prompts import build_prompt
from pcalmd.ai.provider import AIProvider
from pcalmd.ai.rate_limiter import RateLimiter

__all__ = ["AIProvider", "RateLimiter", "build_prompt"]
