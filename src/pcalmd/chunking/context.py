"""Context window construction for pCalmd-AI chunks.

Builds a context preamble that is prepended to each chunk before it is
sent to the AI model.  The preamble gives the model enough surrounding
information (imports, globals, signatures, prior renames) to produce
meaningful deobfuscation even when operating on an isolated slice of the
original file.
"""

from __future__ import annotations

from pcalmd.parser.ast_types import GlobalContext

from .chunker import Chunk, Chunker


class ContextBuilder:
    """Builds context preambles for chunks.

    Each chunk gets a context window prepended with:

    * Import statements from the file
    * Relevant global variable declarations
    * Function / class signatures referenced from the chunk
    * Already-established rename mappings (from previous chunks)
    """

    def __init__(self, max_context_tokens: int = 1000) -> None:
        self.max_context_tokens = max_context_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_context(
        self,
        chunk: Chunk,
        global_ctx: GlobalContext,
        rename_map: dict[str, str] | None = None,
    ) -> str:
        """Build a context preamble string for *chunk*.

        Sections are included in priority order and each section is only
        added if the accumulated token count still fits within the budget:

        1. ``// === FILE CONTEXT ===`` header
        2. ``// Imports:`` + import statements
        3. ``// Global Variables:`` + globals referenced in the chunk
        4. ``// Function Signatures:`` + signatures defined elsewhere
        5. ``// Rename Map:`` + existing rename mappings (if any)
        6. ``// === END CONTEXT ===`` footer

        Priority: imports > globals > signatures > rename map.

        Parameters
        ----------
        chunk:
            The chunk that needs context.
        global_ctx:
            File-wide metadata extracted by the parser.
        rename_map:
            Mapping of original names to deobfuscated names established
            by earlier chunks.  May be *None* or empty.

        Returns
        -------
        str
            The assembled context preamble.
        """
        header = "// === FILE CONTEXT ==="
        footer = "// === END CONTEXT ==="

        # We always include header + footer; their token cost is tiny but
        # we still track it honestly.
        parts: list[str] = [header]
        used_tokens = Chunker.estimate_tokens(header) + Chunker.estimate_tokens(footer)

        # -- 1. Imports ------------------------------------------------
        if global_ctx.imports:
            section = self._format_section("Imports", global_ctx.imports)
            section_tokens = Chunker.estimate_tokens(section)
            if used_tokens + section_tokens <= self.max_context_tokens:
                parts.append(section)
                used_tokens += section_tokens

        # -- 2. Global Variables (only those referenced in chunk) -------
        if global_ctx.global_variables:
            referenced = self._find_referenced_names(
                chunk, global_ctx.global_variables
            )
            if referenced:
                section = self._format_section("Global Variables", referenced)
                section_tokens = Chunker.estimate_tokens(section)
                if used_tokens + section_tokens <= self.max_context_tokens:
                    parts.append(section)
                    used_tokens += section_tokens

        # -- 3. Function Signatures ------------------------------------
        if global_ctx.function_signatures:
            referenced_sigs = self._find_referenced_names(
                chunk, global_ctx.function_signatures
            )
            if referenced_sigs:
                section = self._format_section(
                    "Function Signatures", referenced_sigs
                )
                section_tokens = Chunker.estimate_tokens(section)
                if used_tokens + section_tokens <= self.max_context_tokens:
                    parts.append(section)
                    used_tokens += section_tokens

        # -- 4. Rename Map ---------------------------------------------
        if rename_map:
            rename_lines = [
                f"//   {old} -> {new}" for old, new in rename_map.items()
            ]
            section = "// Rename Map:\n" + "\n".join(rename_lines)
            section_tokens = Chunker.estimate_tokens(section)
            if used_tokens + section_tokens <= self.max_context_tokens:
                parts.append(section)
                used_tokens += section_tokens

        parts.append(footer)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_referenced_names(
        chunk: Chunk,
        all_names: list[str],
    ) -> list[str]:
        """Return entries from *all_names* that appear in *chunk.source*.

        Uses simple substring matching -- if any token-like word from a
        name entry is found in the chunk source, the entry is considered
        referenced.  This is intentionally broad to avoid missing context
        that the AI might need.
        """
        referenced: list[str] = []
        for name in all_names:
            if name in chunk.source:
                referenced.append(name)
        return referenced

    @staticmethod
    def _format_section(heading: str, items: list[str]) -> str:
        """Format a context section with a heading and indented items."""
        lines = [f"// {heading}:"]
        for item in items:
            # Indent each line of multi-line items.
            for line in item.splitlines():
                lines.append(f"//   {line}")
        return "\n".join(lines)
