"""AST structure verification for AI-generated code.

Compares the AST structure of the original and transformed code to detect
hallucinations, accidental deletions, or structural corruption introduced
by the AI model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pcalmd.parser.js_parser import JSParser


@dataclass
class VerifyResult:
    """Outcome of an AST verification check."""

    ok: bool
    """Whether the verification passed."""
    violations: list[str]
    """Human-readable descriptions of any violations found."""


class ASTVerifier:
    """Compares original and transformed code AST structures."""

    def __init__(self) -> None:
        self._parser = JSParser()

    def verify_simplify(self, original: str, transformed: str) -> VerifyResult:
        """Verify that simplification preserved structure.

        Rules:
        - Node count of transformed must be ≤ original
        - All function/class declarations in original must still exist
        """
        orig_units = self._parser.extract_units(original)
        trans_units = self._parser.extract_units(transformed)

        violations: list[str] = []

        # Node count check.
        orig_count = sum(u.children_count for u in orig_units)
        trans_count = sum(u.children_count for u in trans_units)
        if trans_count > orig_count:
            violations.append(
                f"Node count increased: {orig_count} -> {trans_count}"
            )

        # Function/class declarations must be preserved.
        orig_decls = {
            u.name
            for u in orig_units
            if u.node_type
            in (
                "function_declaration",
                "generator_function_declaration",
                "class_declaration",
            )
            and u.name
        }
        trans_decls = {
            u.name
            for u in trans_units
            if u.node_type
            in (
                "function_declaration",
                "generator_function_declaration",
                "class_declaration",
            )
            and u.name
        }
        missing = orig_decls - trans_decls
        if missing:
            violations.append(
                f"Missing declarations: {', '.join(sorted(missing))}"
            )

        return VerifyResult(ok=not violations, violations=violations)

    def verify_rename(self, original: str, transformed: str) -> VerifyResult:
        """Verify that renaming preserved AST structure.

        Rules:
        - Same number of top-level units
        - Same node types in the same order
        - Only identifier text may differ
        """
        orig_units = self._parser.extract_units(original)
        trans_units = self._parser.extract_units(transformed)

        violations: list[str] = []

        if len(orig_units) != len(trans_units):
            violations.append(
                f"Unit count changed: {len(orig_units)} -> {len(trans_units)}"
            )
            return VerifyResult(ok=False, violations=violations)

        for i, (orig, trans) in enumerate(zip(orig_units, trans_units)):
            if orig.node_type != trans.node_type:
                violations.append(
                    f"Unit {i} type changed: {orig.node_type} -> {trans.node_type}"
                )

        return VerifyResult(ok=not violations, violations=violations)

    def verify_comment(self, original: str, transformed: str) -> VerifyResult:
        """Verify that commenting only added comments.

        Rules:
        - Stripping comments from transformed must yield original code
        """
        stripped = _strip_js_comments(transformed)
        orig_norm = _normalize_whitespace(original)
        trans_norm = _normalize_whitespace(stripped)

        violations: list[str] = []
        if orig_norm != trans_norm:
            violations.append(
                "Code was modified beyond adding comments"
            )

        return VerifyResult(ok=not violations, violations=violations)


def _strip_js_comments(code: str) -> str:
    """Remove JavaScript comments from *code*."""
    # Remove single-line comments.
    code = re.sub(r"//[^\n]*", "", code)
    # Remove multi-line comments.
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return code


def _normalize_whitespace(code: str) -> str:
    """Collapse whitespace for comparison."""
    return re.sub(r"\s+", " ", code).strip()
