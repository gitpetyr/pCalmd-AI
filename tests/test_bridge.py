"""Tests for the Node.js AST bridge."""

import pytest

from pcalmd.bridge import NodeBridge


@pytest.fixture(scope="module")
def bridge():
    """One NodeBridge for the entire test module (avoids repeated startup)."""
    b = NodeBridge()
    yield b
    b.close()


class TestExtractScope:
    def test_global_bindings(self, bridge):
        code = "const x = 1; let y = 2; var z = 3;"
        bindings = bridge.extract_scope(code)
        names = {b.name for b in bindings}
        assert {"x", "y", "z"} <= names

    def test_function_scope(self, bridge):
        code = "function foo(a) { const b = a + 1; return b; }"
        bindings = bridge.extract_scope(code)
        kinds = {b.name: b.kind for b in bindings}
        assert kinds["foo"] == "hoisted"
        assert kinds["a"] == "param"
        assert kinds["b"] == "const"

    def test_same_name_different_scopes(self, bridge):
        code = """
function f1() { const x = 1; return x; }
function f2() { const x = 2; return x; }
"""
        bindings = bridge.extract_scope(code)
        xs = [b for b in bindings if b.name == "x"]
        assert len(xs) == 2
        assert xs[0].scope_start != xs[1].scope_start


class TestSafeRename:
    def test_renames_bindings(self, bridge):
        code = "const _0x1 = 42; console.log(_0x1);"
        renamed, applied = bridge.safe_rename(code, {"_0x1": "answer"})
        assert "answer" in renamed
        assert "_0x1" not in renamed
        assert applied["_0x1"] == "answer"

    def test_does_not_touch_strings(self, bridge):
        code = 'const _0x1 = "_0x1"; console.log(_0x1);'
        renamed, _ = bridge.safe_rename(code, {"_0x1": "value"})
        assert '"_0x1"' in renamed  # string literal preserved
        assert "const value" in renamed  # binding renamed

    def test_scope_aware_rename(self, bridge):
        code = """
function outer() {
    const _0x1 = 1;
    function inner() {
        const _0x1 = 2;
        return _0x1;
    }
    return _0x1 + inner();
}
"""
        renamed, _ = bridge.safe_rename(code, {"_0x1": "val"})
        # Both should be renamed since babel handles per-scope
        assert renamed.count("val") >= 4  # 2 declarations + 2 references


class TestVerifyAST:
    def test_rename_valid(self, bridge):
        orig = "function foo(x) { return x + 1; }"
        trans = "function bar(y) { return y + 1; }"
        result = bridge.verify_ast(orig, trans, "rename")
        assert result.ok

    def test_rename_invalid_extra_node(self, bridge):
        orig = "function foo(x) { return x; }"
        trans = "function foo(x) { return x; }\nfunction extra() {}"
        result = bridge.verify_ast(orig, trans, "rename")
        assert not result.ok

    def test_simplify_valid(self, bridge):
        orig = "function foo() { if (true) { return 1; } return 2; }"
        trans = "function foo() { return 1; }"
        result = bridge.verify_ast(orig, trans, "simplify")
        assert result.ok

    def test_simplify_invalid_missing_decl(self, bridge):
        orig = "function foo() {} function bar() {}"
        trans = "function foo() {}"
        result = bridge.verify_ast(orig, trans, "simplify")
        assert not result.ok
        assert any("bar" in v for v in result.violations)

    def test_comment_valid(self, bridge):
        orig = "const x = 1;"
        trans = "// x is the answer\nconst x = 1;"
        result = bridge.verify_ast(orig, trans, "comment")
        assert result.ok

    def test_comment_invalid_code_changed(self, bridge):
        orig = "const x = 1;"
        trans = "// comment\nconst x = 2;"
        result = bridge.verify_ast(orig, trans, "comment")
        assert not result.ok
