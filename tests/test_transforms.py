"""Tests for transforms (mocked AI provider)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pcalmd.config import AISettings
from pcalmd.ai.provider import AIProvider
from pcalmd.transforms.base import TransformResult
from pcalmd.transforms.simplify import SimplifyTransform
from pcalmd.transforms.rename import RenameTransform, _parse_rename_response
from pcalmd.transforms.comment import CommentTransform
from pcalmd.transforms.explain import ExplainTransform


@pytest.fixture
def mock_provider():
    provider = AIProvider(AISettings())
    provider.complete = AsyncMock()
    return provider


class TestSimplifyTransform:
    @pytest.mark.asyncio
    async def test_returns_simplified_code(self, mock_provider):
        mock_provider.complete.return_value = "var a = 3;"
        t = SimplifyTransform(mock_provider)
        result = await t.apply("var a = 1 + 2;")
        assert result.code == "var a = 3;"

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self, mock_provider):
        mock_provider.complete.return_value = "```javascript\nvar a = 3;\n```"
        t = SimplifyTransform(mock_provider)
        result = await t.apply("var a = 1 + 2;")
        assert result.code == "var a = 3;"


class TestRenameTransform:
    @pytest.mark.asyncio
    async def test_returns_renamed_code_and_map(self, mock_provider):
        mock_provider.complete.return_value = (
            'var userName = "test";\n'
            'RENAME_MAP: {"_0x1a": "userName"}'
        )
        t = RenameTransform(mock_provider)
        result = await t.apply('var _0x1a = "test";')
        assert "userName" in result.code
        assert result.rename_map == {"_0x1a": "userName"}

    def test_parse_rename_response_with_map(self):
        resp = 'var x = 1;\nRENAME_MAP: {"a": "b"}'
        code, rmap = _parse_rename_response(resp)
        assert code == "var x = 1;"
        assert rmap == {"a": "b"}

    def test_parse_rename_response_no_map(self):
        resp = "var x = 1;"
        code, rmap = _parse_rename_response(resp)
        assert code == "var x = 1;"
        assert rmap == {}


class TestCommentTransform:
    @pytest.mark.asyncio
    async def test_returns_commented_code(self, mock_provider):
        mock_provider.complete.return_value = "// adds numbers\nvar a = 1 + 2;"
        t = CommentTransform(mock_provider)
        result = await t.apply("var a = 1 + 2;")
        assert "//" in result.code


class TestExplainTransform:
    @pytest.mark.asyncio
    async def test_returns_explanation(self, mock_provider):
        mock_provider.complete.return_value = "This code adds two numbers."
        t = ExplainTransform(mock_provider)
        result = await t.apply("var a = 1 + 2;")
        # Explain keeps original code and stores explanation.
        assert result.code == "var a = 1 + 2;"
        assert result.explanation == "This code adds two numbers."
