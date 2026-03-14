"""Rename transform -- replace obfuscated identifiers with meaningful names."""

from __future__ import annotations

import json
import re

from pcalmd.ai.prompts import build_prompt

from .base import Transform, TransformResult


class RenameTransform(Transform):
    """Renames obfuscated variables/functions to meaningful names."""

    task_name = "rename"

    async def apply(
        self,
        code: str,
        context: str = "",
        *,
        conservative: bool = False,
        rename_map: dict[str, str] | None = None,
    ) -> TransformResult:
        system, user = build_prompt(
            task="rename",
            code=code,
            context=context,
            rename_map=rename_map,
            conservative=conservative,
        )
        result = await self.provider.complete(user, system=system)
        transformed_code, new_renames = _parse_rename_response(result)
        return TransformResult(code=transformed_code, rename_map=new_renames)


def _parse_rename_response(response: str) -> tuple[str, dict[str, str]]:
    """Parse AI response that contains code + ``RENAME_MAP: {...}``."""
    response = response.strip()

    # Strip markdown fences.
    if response.startswith("```"):
        first_nl = response.index("\n")
        response = response[first_nl + 1 :]
    if response.endswith("```"):
        response = response[:-3].strip()

    # Look for the rename map line.
    match = re.search(r"RENAME_MAP:\s*(\{.*\})\s*$", response, re.DOTALL)
    if match:
        code = response[: match.start()].strip()
        try:
            rename_map = json.loads(match.group(1))
            if isinstance(rename_map, dict):
                return code, rename_map
        except json.JSONDecodeError:
            pass
        return code, {}

    return response, {}
