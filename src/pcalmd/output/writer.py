"""Output writer -- file, stdout, or unified diff."""

from __future__ import annotations

import difflib
from pathlib import Path

from rich.console import Console


class OutputWriter:
    """Writes deobfuscated results in the configured format."""

    def __init__(
        self,
        fmt: str = "file",
        suffix: str = ".deobfuscated",
    ) -> None:
        self.fmt = fmt
        self.suffix = suffix
        self._console = Console()

    def write(
        self,
        result: str,
        source_path: Path,
        output_path: Path | None = None,
        original: str | None = None,
    ) -> Path | None:
        """Write *result* according to the configured format.

        Parameters
        ----------
        result:
            The deobfuscated JavaScript source.
        source_path:
            Path to the original input file.
        output_path:
            Explicit output path (overrides format-based naming).
        original:
            Original source text (required for diff format).

        Returns
        -------
        Path | None
            The path written to, or None for stdout/diff.
        """
        match self.fmt:
            case "file":
                return self._write_file(result, source_path, output_path)
            case "stdout":
                self._console.print(result, highlight=False)
                return None
            case "diff":
                self._write_diff(result, source_path, original or "")
                return None
            case _:
                raise ValueError(f"Unknown output format: {self.fmt!r}")

    def _write_file(
        self,
        result: str,
        source_path: Path,
        output_path: Path | None,
    ) -> Path:
        if output_path is None:
            stem = source_path.stem
            ext = source_path.suffix
            output_path = source_path.with_name(f"{stem}{self.suffix}{ext}")
        output_path.write_text(result, encoding="utf-8")
        return output_path

    def _write_diff(
        self, result: str, source_path: Path, original: str
    ) -> None:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            result.splitlines(keepends=True),
            fromfile=str(source_path),
            tofile=str(source_path) + " (deobfuscated)",
        )
        self._console.print("".join(diff), highlight=False)
