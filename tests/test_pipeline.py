"""Tests for the pipeline module."""

from __future__ import annotations

from pathlib import Path

import pytest

from pcalmd.config import Settings
from pcalmd.pipeline import Pipeline


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestAnalyze:
    def test_analyze_simple(self, simple_obfuscated_js):
        settings = Settings()
        pipeline = Pipeline(settings)
        result = pipeline.analyze(simple_obfuscated_js)
        assert result.total_lines > 0
        assert result.units > 0
        assert result.chunks > 0

    def test_analyze_empty(self, empty_js):
        settings = Settings()
        pipeline = Pipeline(settings)
        result = pipeline.analyze(empty_js)
        assert result.units == 0
        assert result.chunks == 0

    def test_analyze_chunk_details(self, simple_obfuscated_js):
        settings = Settings()
        pipeline = Pipeline(settings)
        result = pipeline.analyze(simple_obfuscated_js)
        for cd in result.chunk_details:
            assert "index" in cd
            assert "units" in cd
            assert "tokens_est" in cd


class TestReassemble:
    def test_reassemble_preserves_content(self):
        """Reassembly should produce identical output when chunks are unchanged."""
        source = "var a = 1;\n\nvar b = 2;\n"
        settings = Settings()
        pipeline = Pipeline(settings)
        from pcalmd.parser import JSParser
        from pcalmd.chunking import Chunker

        parser = JSParser()
        units = parser.extract_units(source)
        chunker = Chunker(max_tokens=5000)
        chunks = chunker.chunk(units, source)

        processed = {c.index: c.source for c in chunks}
        result = Pipeline._reassemble(chunks, processed, source)
        assert result == source
