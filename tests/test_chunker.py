"""Tests for the chunking module."""

from pcalmd.chunking import Chunk, Chunker, ContextBuilder
from pcalmd.parser import GlobalContext, JSParser


class TestChunker:
    def setup_method(self):
        self.parser = JSParser()

    def test_single_chunk_when_fits(self):
        source = "var a = 1;\nvar b = 2;"
        units = self.parser.extract_units(source)
        chunker = Chunker(max_tokens=5000)
        chunks = chunker.chunk(units, source)
        assert len(chunks) == 1
        assert len(chunks[0].units) == 2

    def test_splits_at_budget_boundary(self):
        # Create source with many functions that should force splitting.
        funcs = [f"function f{i}() {{ return {i}; }}" for i in range(20)]
        source = "\n".join(funcs)
        units = self.parser.extract_units(source)
        chunker = Chunker(max_tokens=50)  # Very small budget.
        chunks = chunker.chunk(units, source)
        assert len(chunks) > 1

    def test_never_splits_single_unit(self):
        # One large function.
        body = "; ".join([f"var x{i} = {i}" for i in range(100)])
        source = f"function big() {{ {body}; }}"
        units = self.parser.extract_units(source)
        chunker = Chunker(max_tokens=10)
        chunks = chunker.chunk(units, source)
        assert len(chunks) == 1
        assert chunks[0].is_oversized is True

    def test_preserves_inter_unit_whitespace(self):
        source = "var a = 1;\n\n// gap\n\nvar b = 2;"
        units = self.parser.extract_units(source)
        chunker = Chunker(max_tokens=5000)
        chunks = chunker.chunk(units, source)
        assert "// gap" in chunks[0].source

    def test_empty_units(self):
        chunker = Chunker()
        chunks = chunker.chunk([], "")
        assert chunks == []

    def test_chunk_byte_offsets(self, simple_obfuscated_js):
        units = self.parser.extract_units(simple_obfuscated_js)
        chunker = Chunker(max_tokens=100)
        chunks = chunker.chunk(units, simple_obfuscated_js)
        for chunk in chunks:
            assert chunk.start_byte < chunk.end_byte

    def test_estimate_tokens(self):
        assert Chunker.estimate_tokens("") == 1
        assert Chunker.estimate_tokens("a" * 100) == 25
        assert Chunker.estimate_tokens("a" * 4) == 1


class TestContextBuilder:
    def test_builds_context_with_imports(self):
        from pcalmd.chunking.chunker import Chunk
        from pcalmd.parser.ast_types import CodeUnit

        unit = CodeUnit(
            node_type="expression_statement",
            name=None,
            source="console.log(foo);",
            start_byte=0,
            end_byte=17,
            start_point=(0, 0),
            end_point=(0, 17),
            children_count=1,
        )
        chunk = Chunk(
            index=0, units=[unit], source="console.log(foo);",
            start_byte=0, end_byte=17, is_oversized=False,
        )
        ctx = GlobalContext(
            imports=['import { foo } from "bar";'],
            total_lines=1,
            total_bytes=17,
        )
        builder = ContextBuilder(max_context_tokens=1000)
        result = builder.build_context(chunk, ctx)
        assert "FILE CONTEXT" in result
        assert "foo" in result
        assert "END CONTEXT" in result

    def test_context_includes_rename_map(self):
        from pcalmd.chunking.chunker import Chunk
        from pcalmd.parser.ast_types import CodeUnit

        unit = CodeUnit(
            node_type="expression_statement",
            name=None,
            source="x()",
            start_byte=0, end_byte=3,
            start_point=(0, 0), end_point=(0, 3),
            children_count=1,
        )
        chunk = Chunk(
            index=0, units=[unit], source="x()",
            start_byte=0, end_byte=3, is_oversized=False,
        )
        ctx = GlobalContext(total_lines=1, total_bytes=3)
        builder = ContextBuilder()
        result = builder.build_context(chunk, ctx, rename_map={"_0x1": "userName"})
        assert "Rename Map" in result
        assert "userName" in result
