"""Explain transform -- generate natural-language explanation of code."""

from __future__ import annotations

from pcalmd.ai.prompts import build_prompt

from .base import Transform, TransformResult


class ExplainTransform(Transform):
    """Generates a human-readable explanation of what the code does."""

    task_name = "explain"

    async def apply(
        self,
        code: str,
        context: str = "",
        *,
        conservative: bool = False,
        rename_map: dict[str, str] | None = None,
    ) -> TransformResult:
        system, user = build_prompt(
            task="explain",
            code=code,
            context=context,
            conservative=conservative,
        )
        result = await self.provider.complete(user, system=system)
        # Explain returns prose, not code — store it as explanation.
        return TransformResult(code=code, explanation=result.strip())
