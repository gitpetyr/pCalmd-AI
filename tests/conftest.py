"""Shared test fixtures for pCalmd-AI."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_obfuscated_js() -> str:
    """Return the simple obfuscated JS fixture as a string."""
    return (FIXTURES_DIR / "simple_obfuscated.js").read_text(encoding="utf-8")


@pytest.fixture
def empty_js() -> str:
    return ""


@pytest.fixture
def comment_only_js() -> str:
    return "// just a comment\n/* block comment */\n"
