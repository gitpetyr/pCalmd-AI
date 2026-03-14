"""JavaScript parser backed by tree-sitter.

Provides :class:`JSParser`, the primary entry point for turning raw
JavaScript source code into structured :class:`CodeUnit` and
:class:`GlobalContext` objects.
"""

from __future__ import annotations

import tree_sitter as ts
import tree_sitter_javascript as tsjs

from .ast_types import CodeUnit, GlobalContext

# Build the Language object once at module level.
_JS_LANGUAGE = ts.Language(tsjs.language())


class JSParser:
    """Wraps tree-sitter to parse JavaScript source code."""

    def __init__(self) -> None:
        self._parser = ts.Parser(_JS_LANGUAGE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, source: str | bytes) -> ts.Tree:
        """Parse *source* into a tree-sitter ``Tree``.

        Parameters
        ----------
        source:
            JavaScript source code as ``str`` or ``bytes``.

        Returns
        -------
        tree_sitter.Tree
            The parsed syntax tree.
        """
        source_bytes = source.encode("utf-8") if isinstance(source, str) else source
        return self._parser.parse(source_bytes)

    def extract_units(self, source: str | bytes) -> list[CodeUnit]:
        """Extract top-level :class:`CodeUnit` instances from *source*.

        Each named child of the root ``program`` node becomes one
        ``CodeUnit``.  The list is sorted by ``start_byte``.
        """
        source_bytes = source.encode("utf-8") if isinstance(source, str) else source
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        units: list[CodeUnit] = []
        for child in root.named_children:
            unit = CodeUnit(
                node_type=child.type,
                name=self._extract_name(child),
                source=child.text.decode("utf-8") if child.text else "",
                start_byte=child.start_byte,
                end_byte=child.end_byte,
                start_point=(child.start_point[0], child.start_point[1]),
                end_point=(child.end_point[0], child.end_point[1]),
                children_count=child.child_count,
            )
            units.append(unit)

        units.sort(key=lambda u: u.start_byte)
        return units

    def extract_global_context(self, source: str | bytes) -> GlobalContext:
        """Extract :class:`GlobalContext` from *source*.

        Categories
        ----------
        * **imports** -- ``import`` statements and top-level ``require()``
          calls.
        * **global_variables** -- ``var`` / ``let`` / ``const``
          declarations at the top level.
        * **function_signatures** -- function / class signatures without
          their body.
        """
        source_bytes = source.encode("utf-8") if isinstance(source, str) else source
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        imports: list[str] = []
        global_variables: list[str] = []
        function_signatures: list[str] = []

        for child in root.named_children:
            node_text = child.text.decode("utf-8") if child.text else ""
            ntype = child.type

            # -- Imports -------------------------------------------------
            if ntype == "import_statement":
                imports.append(node_text)
                continue

            # Top-level require():  expression_statement wrapping a
            # call_expression whose function is "require", OR a
            # variable declaration whose initialiser is require().
            if self._is_require(child):
                imports.append(node_text)
                continue

            # -- Variable declarations -----------------------------------
            if ntype in ("variable_declaration", "lexical_declaration"):
                # Check if this is a require-based import already handled.
                # If the declaration contains an arrow/function expression,
                # also record a signature.
                sig = self._extract_signature(child)
                if sig is not None:
                    function_signatures.append(sig)
                global_variables.append(node_text)
                continue

            # -- Function / class declarations ---------------------------
            if ntype in (
                "function_declaration",
                "generator_function_declaration",
                "class_declaration",
            ):
                sig = self._extract_signature(child)
                if sig is not None:
                    function_signatures.append(sig)
                continue

            # -- Expression statements that assign functions/classes ------
            if ntype == "expression_statement":
                sig = self._extract_signature(child)
                if sig is not None:
                    function_signatures.append(sig)
                continue

        # Count lines: newline-terminated files have count(b"\n") lines,
        # files without a trailing newline have one extra partial line,
        # and empty files have 0 lines.
        if not source_bytes:
            total_lines = 0
        elif source_bytes.endswith(b"\n"):
            total_lines = source_bytes.count(b"\n")
        else:
            total_lines = source_bytes.count(b"\n") + 1

        return GlobalContext(
            imports=imports,
            global_variables=global_variables,
            function_signatures=function_signatures,
            total_lines=total_lines,
            total_bytes=len(source_bytes),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_name(self, node: ts.Node) -> str | None:
        """Extract the identifier name from a declaration node.

        Returns ``None`` when no name can be determined.
        """
        ntype = node.type

        # function_declaration / generator_function_declaration / class_declaration
        if ntype in (
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
        ):
            name_node = node.child_by_field_name("name")
            if name_node and name_node.text:
                return name_node.text.decode("utf-8")
            return None

        # variable_declaration / lexical_declaration
        if ntype in ("variable_declaration", "lexical_declaration"):
            for child in node.named_children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node and name_node.text:
                        return name_node.text.decode("utf-8")
            return None

        # expression_statement with assignment_expression
        if ntype == "expression_statement":
            expr = self._get_inner_expression(node)
            if expr is not None and expr.type == "assignment_expression":
                left = expr.child_by_field_name("left")
                if left and left.text:
                    return left.text.decode("utf-8")
            return None

        # export_statement -- look inside for the actual declaration
        if ntype == "export_statement":
            for child in node.named_children:
                name = self._extract_name(child)
                if name is not None:
                    return name
            return None

        return None

    def _extract_signature(self, node: ts.Node) -> str | None:
        """Extract a human-readable signature without the body.

        Returns ``None`` when the node does not represent a function or
        class that warrants a signature.
        """
        ntype = node.type

        # function_declaration / generator_function_declaration
        if ntype in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            params_node = node.child_by_field_name("parameters")
            prefix = "function*" if "generator" in ntype else "function"
            name = name_node.text.decode("utf-8") if name_node and name_node.text else ""
            params = params_node.text.decode("utf-8") if params_node and params_node.text else "()"
            return f"{prefix} {name}{params}"

        # class_declaration
        if ntype == "class_declaration":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node and name_node.text else ""
            # Check for heritage (extends)
            heritage = None
            for child in node.named_children:
                if child.type == "class_heritage":
                    heritage = child.text.decode("utf-8") if child.text else None
                    break
            if heritage:
                return f"class {name} {heritage}"
            return f"class {name}"

        # variable_declaration / lexical_declaration with arrow or function
        if ntype in ("variable_declaration", "lexical_declaration"):
            return self._signature_from_var_decl(node)

        # expression_statement wrapping an assignment to a function
        if ntype == "expression_statement":
            expr = self._get_inner_expression(node)
            if expr is not None and expr.type == "assignment_expression":
                right = expr.child_by_field_name("right")
                left = expr.child_by_field_name("left")
                if right and left and left.text:
                    lhs = left.text.decode("utf-8")
                    if right.type == "arrow_function":
                        params = right.child_by_field_name("parameters")
                        p_text = params.text.decode("utf-8") if params and params.text else "()"
                        return f"{lhs} = {p_text} => ..."
                    if right.type == "function_expression":
                        params = right.child_by_field_name("parameters")
                        p_text = params.text.decode("utf-8") if params and params.text else "()"
                        return f"{lhs} = function{p_text}"
            return None

        return None

    def _signature_from_var_decl(self, node: ts.Node) -> str | None:
        """Build a signature for ``const f = (...) => ...`` patterns."""
        # Determine keyword (const / let / var)
        keyword = ""
        for child in node.children:
            if child.type in ("const", "let", "var"):
                keyword = child.type
                break

        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if not name_node or not name_node.text or not value_node:
                continue

            var_name = name_node.text.decode("utf-8")

            if value_node.type == "arrow_function":
                params = value_node.child_by_field_name("parameters")
                p_text = params.text.decode("utf-8") if params and params.text else "()"
                return f"{keyword} {var_name} = {p_text} => ..." if keyword else f"{var_name} = {p_text} => ..."

            if value_node.type == "function_expression":
                params = value_node.child_by_field_name("parameters")
                p_text = params.text.decode("utf-8") if params and params.text else "()"
                return f"{keyword} {var_name} = function{p_text}" if keyword else f"{var_name} = function{p_text}"

        return None

    def _is_require(self, node: ts.Node) -> bool:
        """Return ``True`` when *node* represents a ``require()`` call.

        Handles both bare ``require("x")`` expression statements and
        ``const x = require("x")`` variable declarations.
        """
        ntype = node.type

        # expression_statement wrapping require(...)
        if ntype == "expression_statement":
            expr = self._get_inner_expression(node)
            if expr is not None and expr.type == "call_expression":
                fn = expr.child_by_field_name("function")
                if fn and fn.text == b"require":
                    return True
            return False

        # variable / lexical declaration with require(...)
        if ntype in ("variable_declaration", "lexical_declaration"):
            for child in node.named_children:
                if child.type == "variable_declarator":
                    value = child.child_by_field_name("value")
                    if value and value.type == "call_expression":
                        fn = value.child_by_field_name("function")
                        if fn and fn.text == b"require":
                            return True
            return False

        return False

    @staticmethod
    def _get_inner_expression(expr_stmt: ts.Node) -> ts.Node | None:
        """Return the first named child of an ``expression_statement``."""
        children = expr_stmt.named_children
        return children[0] if children else None
