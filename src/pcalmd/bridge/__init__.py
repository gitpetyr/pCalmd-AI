"""Node.js AST bridge for pCalmd-AI.

Provides scope-aware renaming, deep AST verification, and scope
extraction by delegating to a long-running Node.js child process
that uses Babel + recast.
"""

from .node_bridge import NodeBridge

__all__ = ["NodeBridge"]
