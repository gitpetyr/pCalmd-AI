"""Base class for all pCalmd-AI transforms."""

from __future__ import annotations

import abc

from pcalmd.ai.provider import AIProvider
from pcalmd.chunking.chunker import Chunk


class Transform(abc.ABC):
    """Abstract base for a single deobfuscation transform.

    Subclasses implement :meth:`apply` which takes a chunk's source code
    (with context prepended) and returns the transformed code.
    """

    # Subclasses set this to their task name ("simplify", "rename", etc.)
    task_name: str = ""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    @abc.abstractmethod
    async def apply(
        self,
        code: str,
        context: str = "",
        *,
        conservative: bool = False,
        rename_map: dict[str, str] | None = None,
    ) -> TransformResult:
        """Apply this transform to *code*.

        Parameters
        ----------
        code:
            JavaScript source to transform.
        context:
            Context preamble for the AI.
        conservative:
            Use conservative prompt for oversized chunks.
        rename_map:
            Existing renames (only used by the rename transform).

        Returns
        -------
        TransformResult
            The transformed code and any metadata.
        """


class TransformResult:
    """Result returned by a transform."""

    __slots__ = ("code", "rename_map", "explanation")

    def __init__(
        self,
        code: str,
        rename_map: dict[str, str] | None = None,
        explanation: str | None = None,
    ) -> None:
        self.code = code
        self.rename_map = rename_map
        self.explanation = explanation
