"""Tests for the parser module."""

from pcalmd.parser import CodeUnit, GlobalContext, JSParser


class TestJSParser:
    def setup_method(self):
        self.parser = JSParser()

    def test_parse_returns_tree(self):
        tree = self.parser.parse("var x = 1;")
        assert tree.root_node.type == "program"

    def test_extract_units_function(self):
        units = self.parser.extract_units("function foo(x) { return x; }")
        assert len(units) == 1
        assert units[0].node_type == "function_declaration"
        assert units[0].name == "foo"

    def test_extract_units_class(self):
        units = self.parser.extract_units("class MyClass { method() {} }")
        assert len(units) == 1
        assert units[0].node_type == "class_declaration"
        assert units[0].name == "MyClass"

    def test_extract_units_variable(self):
        units = self.parser.extract_units("const x = 42;")
        assert len(units) == 1
        assert units[0].name == "x"

    def test_extract_units_multiple(self, simple_obfuscated_js):
        units = self.parser.extract_units(simple_obfuscated_js)
        assert len(units) > 5
        names = [u.name for u in units if u.name]
        assert "_0x5e6f" in names
        assert "_0xAbCd" in names

    def test_extract_units_empty(self, empty_js):
        units = self.parser.extract_units(empty_js)
        assert units == []

    def test_extract_units_preserves_byte_offsets(self):
        source = "var a = 1;\nvar b = 2;"
        units = self.parser.extract_units(source)
        assert len(units) == 2
        assert units[0].start_byte == 0
        assert units[1].start_byte > units[0].end_byte

    def test_extract_global_context_imports(self):
        source = 'import { foo } from "bar";\nconst x = require("y");'
        ctx = self.parser.extract_global_context(source)
        assert len(ctx.imports) == 2

    def test_extract_global_context_signatures(self):
        source = "function greet(name) { return name; }\nconst add = (a, b) => a + b;"
        ctx = self.parser.extract_global_context(source)
        assert len(ctx.function_signatures) == 2

    def test_extract_global_context_counts(self, simple_obfuscated_js):
        ctx = self.parser.extract_global_context(simple_obfuscated_js)
        assert ctx.total_lines > 0
        assert ctx.total_bytes > 0

    def test_code_unit_fields(self):
        units = self.parser.extract_units("function test() {}")
        u = units[0]
        assert isinstance(u, CodeUnit)
        assert isinstance(u.start_point, tuple)
        assert isinstance(u.end_point, tuple)
        assert u.children_count > 0
