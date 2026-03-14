"""LiteLLM multi-provider wrapper for AI completions."""

from __future__ import annotations

import litellm

from pcalmd.config import AISettings


# Provider name -> LiteLLM model prefix mapping.
_PROVIDER_PREFIXES: dict[str, str] = {
    "anthropic": "anthropic/",
    "openai": "openai/",
    "gemini": "gemini/",
}


class AIProvider:
    """Wraps LiteLLM for multi-provider AI completions."""

    def __init__(self, settings: AISettings) -> None:
        self.settings = settings
        self._configure()

    def _configure(self) -> None:
        """Configure LiteLLM based on provider settings.

        - Set api_key via litellm module-level vars or environment
        - For 'custom' provider, set api_base
        - Map provider names to LiteLLM model prefixes:
            anthropic -> "anthropic/{model}" (if not already prefixed)
            openai -> "openai/{model}" (if not already prefixed)
            gemini -> "gemini/{model}" (if not already prefixed)
            custom -> "{model}" with api_base set
        """
        provider = self.settings.provider.lower()

        if self.settings.api_key:
            litellm.api_key = self.settings.api_key

        if provider == "custom" and self.settings.api_base:
            litellm.api_base = self.settings.api_base

    @property
    def model_name(self) -> str:
        """Return the full LiteLLM model name with provider prefix."""
        provider = self.settings.provider.lower()
        model = self.settings.model

        if provider == "custom":
            return model

        prefix = _PROVIDER_PREFIXES.get(provider, "")
        if prefix and not model.startswith(prefix):
            return f"{prefix}{model}"
        return model

    async def complete(self, prompt: str, system: str | None = None) -> str:
        """Send a completion request and return the response text.

        Uses litellm.acompletion() for async support.

        Parameters
        ----------
        prompt:
            The user message.
        system:
            Optional system message.

        Returns
        -------
        str
            The assistant's response text.

        Raises
        ------
        Exception
            API errors are allowed to propagate.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await litellm.acompletion(
            model=self.model_name,
            messages=messages,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
        )
        return response.choices[0].message.content
