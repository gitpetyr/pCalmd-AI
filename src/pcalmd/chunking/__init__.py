"""Chunking module for pCalmd-AI.

Re-exports the public API surface:

* :class:`Chunk` -- a group of consecutive CodeUnits within a token budget
* :class:`Chunker` -- AST-aware chunking engine
* :class:`ContextBuilder` -- context preamble construction for chunks
"""

from .chunker import Chunk, Chunker
from .context import ContextBuilder

__all__ = ["Chunk", "Chunker", "ContextBuilder"]
