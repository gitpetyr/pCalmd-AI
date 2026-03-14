"""Tests for the verification module."""

from pcalmd.verification import ASTVerifier, GlobalRenameMap


class TestASTVerifier:
    def setup_method(self):
        self.v = ASTVerifier()

    def test_simplify_pass(self):
        original = "function foo() { if (true) { return 1; } }"
        simplified = "function foo() { return 1; }"
        result = self.v.verify_simplify(original, simplified)
        assert result.ok

    def test_simplify_fail_missing_function(self):
        original = "function foo() { return 1; }\nfunction bar() { return 2; }"
        simplified = "function foo() { return 1; }"
        result = self.v.verify_simplify(original, simplified)
        assert not result.ok
        assert any("bar" in v for v in result.violations)

    def test_rename_pass(self):
        original = "var _0x1 = 1;\nvar _0x2 = 2;"
        renamed = "var count = 1;\nvar total = 2;"
        result = self.v.verify_rename(original, renamed)
        assert result.ok

    def test_rename_fail_extra_unit(self):
        original = "var _0x1 = 1;"
        renamed = "var count = 1;\nvar extra = 2;"
        result = self.v.verify_rename(original, renamed)
        assert not result.ok

    def test_comment_pass(self):
        original = "var x = 1;"
        commented = "// sets x\nvar x = 1;"
        result = self.v.verify_comment(original, commented)
        assert result.ok

    def test_comment_fail_code_changed(self):
        original = "var x = 1;"
        commented = "// sets x\nvar x = 2;"
        result = self.v.verify_comment(original, commented)
        assert not result.ok


class TestGlobalRenameMap:
    def test_propose_accept(self):
        m = GlobalRenameMap()
        assert m.propose("_0x1", "userName") is True
        assert m.get("_0x1") == "userName"

    def test_propose_duplicate_same(self):
        m = GlobalRenameMap()
        m.propose("_0x1", "userName")
        assert m.propose("_0x1", "userName") is True

    def test_propose_reject_conflict_old(self):
        m = GlobalRenameMap()
        m.propose("_0x1", "userName")
        assert m.propose("_0x1", "otherName") is False

    def test_propose_reject_conflict_new(self):
        m = GlobalRenameMap()
        m.propose("_0x1", "userName")
        assert m.propose("_0x2", "userName") is False

    def test_merge(self):
        m = GlobalRenameMap()
        accepted = m.merge({"a": "x", "b": "y"})
        assert accepted == {"a": "x", "b": "y"}
        assert len(m) == 2

    def test_apply_to_source(self):
        m = GlobalRenameMap()
        m.propose("_0x1a", "count")
        result = m.apply_to_source("var _0x1a = 0; _0x1a++;")
        assert "count" in result
        assert "_0x1a" not in result

    def test_contains(self):
        m = GlobalRenameMap()
        m.propose("a", "b")
        assert "a" in m
        assert "c" not in m
