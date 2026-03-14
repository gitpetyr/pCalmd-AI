"""Comment transform -- add inline comments explaining code logic."""

from __future__ import annotations

from pcalmd.ai.prompts import build_prompt

from .base import Transform, TransformResult


class CommentTransform(Transform):
    """Adds concise inline comments to explain non-obvious code logic."""

    task_name = "comment"

    async def apply(
        self,
        code: str,
        context: str = "",
        *,
        conservative: bool = False,
        rename_map: dict[str, str] | None = None,
    ) -> TransformResult:
        system, user = build_prompt(
            task="comment",
            code=code,
            context=context,
            conservative=conservative,
        )
        result = await self.provider.complete(user, system=system)
        return TransformResult(code=_strip_fences(result))


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if the AI included them."""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.index("\n")
        text = text[first_nl + 1 :]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
