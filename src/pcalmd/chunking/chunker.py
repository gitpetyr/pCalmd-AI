"""AST-aware chunking for pCalmd-AI.

Groups :class:`CodeUnit` objects into token-budget-constrained chunks
while respecting the core invariant: **never split inside a function or
class body**.  Each chunk is a contiguous sequence of complete top-level
syntactic units.
"""

from __future__ import annotations

from dataclasses import dataclass

from pcalmd.parser.ast_types import CodeUnit


@dataclass
class Chunk:
    """A group of consecutive CodeUnits that fits within the token budget."""

    index: int
    """Chunk sequence number (0-based)."""

    units: list[CodeUnit]
    """The CodeUnits included in this chunk."""

    source: str
    """Concatenated source of all units with inter-unit whitespace preserved."""

    start_byte: int
    """Byte offset of the first unit's start in the original file."""

    end_byte: int
    """Byte offset past the last unit's end in the original file."""

    is_oversized: bool
    """``True`` when a single unit exceeds 80 % of the token budget.

    Signals the downstream pipeline to use conservative / smaller-batch
    processing for this chunk.
    """


class Chunker:
    """Groups CodeUnits into token-budget-constrained chunks.

    CORE RULE: Never split inside a function/class body.
    Each chunk is a contiguous sequence of complete top-level CodeUnits.
    """

    def __init__(self, max_tokens: int = 3000) -> None:
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(
        self,
        units: list[CodeUnit],
        original_source: str | bytes,
    ) -> list[Chunk]:
        """Group *units* into chunks that each fit within the token budget.

        Algorithm
        ---------
        1. Estimate the token count for each unit via the simple ``len / 4``
           heuristic.
        2. Greedily pack consecutive units into chunks until adding the next
           unit would exceed the budget.
        3. If a single unit exceeds the budget it becomes its own chunk --
           it is **never** split.
        4. Mark a chunk as *oversized* when it contains exactly one unit
           whose estimated token count exceeds 80 % of the budget.
        5. Preserve inter-unit whitespace and comments from *original_source*
           when assembling each chunk's ``source`` string.

        Parameters
        ----------
        units:
            Ordered list of :class:`CodeUnit` objects (by byte offset).
        original_source:
            The complete original file content.  Needed to extract the
            bytes between units (comments, blank lines, etc.).

        Returns
        -------
        list[Chunk]
            Chunks sorted by byte offset.
        """
        if not units:
            return []

        # Normalise to str so slice indexing is consistent.
        if isinstance(original_source, bytes):
            original_source = original_source.decode("utf-8", errors="replace")

        oversized_threshold = int(self.max_tokens * 0.8)
        chunks: list[Chunk] = []
        current_units: list[CodeUnit] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = self.estimate_tokens(unit.source)

            if not current_units:
                # First unit in a new chunk -- always accept it.
                current_units.append(unit)
                current_tokens = unit_tokens
                continue

            if current_tokens + unit_tokens <= self.max_tokens:
                # Fits -- add it to the current chunk.
                current_units.append(unit)
                current_tokens += unit_tokens
            else:
                # Would exceed budget -- flush current chunk, start a new one.
                chunks.append(
                    self._build_chunk(
                        index=len(chunks),
                        units=current_units,
                        original_source=original_source,
                        oversized_threshold=oversized_threshold,
                    )
                )
                current_units = [unit]
                current_tokens = unit_tokens

        # Flush the last chunk.
        if current_units:
            chunks.append(
                self._build_chunk(
                    index=len(chunks),
                    units=current_units,
                    original_source=original_source,
                    oversized_threshold=oversized_threshold,
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate: ``len(text) / 4``.

        This is a simple heuristic.  For more accurate counts the AI
        provider module can be used, but for chunking purposes this
        approximation is sufficient.
        """
        return max(1, len(text) // 4)

    @staticmethod
    def _build_chunk(
        index: int,
        units: list[CodeUnit],
        original_source: str,
        oversized_threshold: int,
    ) -> Chunk:
        """Assemble a :class:`Chunk` from its constituent units.

        The chunk's ``source`` includes the original text spanning from
        the first unit's ``start_byte`` to the last unit's ``end_byte``,
        which preserves inter-unit whitespace and comments exactly as
        they appeared in the file.
        """
        start_byte = units[0].start_byte
        end_byte = units[-1].end_byte
        source = original_source[start_byte:end_byte]

        is_oversized = (
            len(units) == 1
            and Chunker.estimate_tokens(units[0].source) > oversized_threshold
        )

        return Chunk(
            index=index,
            units=units,
            source=source,
            start_byte=start_byte,
            end_byte=end_byte,
            is_oversized=is_oversized,
        )
