"""Parser module for pCalmd-AI.

Re-exports the public API surface:

* :class:`JSParser` -- tree-sitter backed JavaScript parser
* :class:`CodeUnit` -- dataclass for a single top-level AST unit
* :class:`GlobalContext` -- dataclass for file-wide context metadata
"""

from .ast_types import CodeUnit, GlobalContext
from .js_parser import JSParser

__all__ = ["JSParser", "CodeUnit", "GlobalContext"]
