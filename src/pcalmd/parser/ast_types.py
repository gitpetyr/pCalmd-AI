"""AST data types for pCalmd-AI parser.

Defines the core data structures produced by parsing JavaScript source
code with tree-sitter.  These types are consumed by the chunking and
transform modules downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodeUnit:
    """A single top-level syntactic unit extracted from the AST.

    Represents a complete function, class, variable declaration,
    import statement, or expression statement at the top level.
    """

    node_type: str
    """tree-sitter node type (e.g. ``"function_declaration"``,
    ``"class_declaration"``, ``"lexical_declaration"``)."""

    name: str | None
    """Identifier name when applicable (function / class / variable).
    ``None`` for expression statements or nodes whose name cannot be
    determined."""

    source: str
    """Original source-code text for this unit."""

    start_byte: int
    """Byte offset of the first character in the original file."""

    end_byte: int
    """Byte offset past the last character in the original file."""

    start_point: tuple[int, int]
    """``(row, column)`` of the first character."""

    end_point: tuple[int, int]
    """``(row, column)`` past the last character."""

    children_count: int
    """Number of AST child nodes (useful for verification)."""


@dataclass
class GlobalContext:
    """Global-scope information extracted from the entire file.

    Provides contextual metadata that the AI can use when processing
    individual code chunks in isolation.
    """

    imports: list[str] = field(default_factory=list)
    """``import`` / ``require`` statements as verbatim source strings."""

    global_variables: list[str] = field(default_factory=list)
    """Top-level variable declaration source strings."""

    function_signatures: list[str] = field(default_factory=list)
    """Function and class signatures (name + params, no body)."""

    total_lines: int = 0
    """Total number of lines in the original source."""

    total_bytes: int = 0
    """Total byte length of the original source."""
