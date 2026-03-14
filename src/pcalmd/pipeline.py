"""Main orchestration pipeline for pCalmd-AI.

Coordinates parsing, chunking, AI transforms, verification, and
reassembly of the deobfuscated JavaScript output.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from pcalmd.ai.provider import AIProvider
from pcalmd.ai.rate_limiter import RateLimiter
from pcalmd.chunking.chunker import Chunk, Chunker
from pcalmd.chunking.context import ContextBuilder
from pcalmd.config import Settings
from pcalmd.parser.ast_types import GlobalContext
from pcalmd.parser.js_parser import JSParser
from pcalmd.transforms.base import Transform, TransformResult
from pcalmd.transforms.comment import CommentTransform
from pcalmd.transforms.explain import ExplainTransform
from pcalmd.transforms.rename import RenameTransform
from pcalmd.transforms.simplify import SimplifyTransform
from pcalmd.bridge.node_bridge import NodeBridge
from pcalmd.verification.ast_verify import ASTVerifier
from pcalmd.verification.rename_map import GlobalRenameMap

console = Console()


@dataclass
class PipelineResult:
    """Final output of the deobfuscation pipeline."""

    code: str
    """The deobfuscated JavaScript source."""
    explanations: list[str] = field(default_factory=list)
    """Per-chunk explanations (if explain was enabled)."""
    warnings: list[str] = field(default_factory=list)
    """Warnings generated during processing."""
    chunks_processed: int = 0
    chunks_failed: int = 0


@dataclass
class AnalysisResult:
    """Result of structural analysis (no AI calls)."""

    total_lines: int
    total_bytes: int
    units: int
    chunks: int
    imports: list[str]
    global_variables: list[str]
    function_signatures: list[str]
    chunk_details: list[dict[str, object]]


class Pipeline:
    """Main deobfuscation pipeline."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._parser = JSParser()
        self._chunker = Chunker(max_tokens=settings.chunking.max_tokens)
        self._ctx_builder = ContextBuilder(
            max_context_tokens=settings.chunking.context_tokens
        )
        self._verifier = ASTVerifier()
        self._rename_map = GlobalRenameMap()
        self._bridge: NodeBridge | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, source: str) -> AnalysisResult:
        """Analyze JS structure without AI calls."""
        units = self._parser.extract_units(source)
        global_ctx = self._parser.extract_global_context(source)
        chunks = self._chunker.chunk(units, source)

        chunk_details = []
        for c in chunks:
            chunk_details.append(
                {
                    "index": c.index,
                    "units": len(c.units),
                    "tokens_est": Chunker.estimate_tokens(c.source),
                    "oversized": c.is_oversized,
                    "start_byte": c.start_byte,
                    "end_byte": c.end_byte,
                    "unit_names": [u.name for u in c.units if u.name],
                }
            )

        return AnalysisResult(
            total_lines=global_ctx.total_lines,
            total_bytes=global_ctx.total_bytes,
            units=len(units),
            chunks=len(chunks),
            imports=global_ctx.imports,
            global_variables=global_ctx.global_variables,
            function_signatures=global_ctx.function_signatures,
            chunk_details=chunk_details,
        )

    async def deobfuscate(self, source: str) -> PipelineResult:
        """Run the full deobfuscation pipeline.

        Steps:
        1. Parse → extract units and global context
        2. Chunk → AST-aware splitting
        3. For each chunk, run enabled transforms (simplify → rename → comment)
        4. Verify each AI output
        5. Reassemble chunks by byte offset
        6. Final consistency pass (apply global rename map)
        """
        cfg = self.settings.pipeline
        provider = AIProvider(self.settings.ai)
        limiter = RateLimiter(
            max_concurrent=self.settings.rate_limit.max_concurrent,
            requests_per_minute=self.settings.rate_limit.requests_per_minute,
        )

        # Start Node bridge for scope-aware rename / deep verification.
        try:
            self._bridge = NodeBridge()
        except RuntimeError:
            self._bridge = None

        # 1. Parse
        units = self._parser.extract_units(source)
        global_ctx = self._parser.extract_global_context(source)

        if not units:
            return PipelineResult(code=source)

        # 2. Chunk
        chunks = self._chunker.chunk(units, source)

        # Build transforms list.
        transforms: list[Transform] = []
        if cfg.simplify:
            transforms.append(SimplifyTransform(provider))
        if cfg.rename:
            transforms.append(RenameTransform(provider))
        if cfg.comment:
            transforms.append(CommentTransform(provider))

        explain_transform = ExplainTransform(provider) if cfg.explain else None

        # 3-4. Process chunks
        processed: dict[int, str] = {}
        explanations: list[str] = []
        warnings: list[str] = []
        failed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task("Processing chunks...", total=len(chunks))

            for chunk in chunks:
                progress.update(
                    task_id,
                    description=f"Chunk {chunk.index + 1}/{len(chunks)}",
                )

                result_code = await self._process_chunk(
                    chunk=chunk,
                    transforms=transforms,
                    global_ctx=global_ctx,
                    limiter=limiter,
                    max_retries=cfg.max_retries,
                    verify=cfg.verify,
                    warnings=warnings,
                )

                if result_code is None:
                    # All retries failed — keep original.
                    processed[chunk.index] = chunk.source
                    failed += 1
                else:
                    processed[chunk.index] = result_code

                # Optional explain pass.
                if explain_transform:
                    ctx_text = self._ctx_builder.build_context(
                        chunk, global_ctx, self._rename_map.mapping
                    )
                    async with limiter:
                        res = await explain_transform.apply(
                            code=processed[chunk.index], context=ctx_text
                        )
                    if res.explanation:
                        explanations.append(
                            f"--- Chunk {chunk.index + 1} ---\n{res.explanation}"
                        )

                progress.advance(task_id)

        # 5. Reassemble
        reassembled = self._reassemble(chunks, processed, source)

        # 6. Final rename consistency pass — scope-aware if bridge available.
        if cfg.rename and len(self._rename_map) > 0:
            if self._bridge:
                reassembled, _ = self._bridge.safe_rename(
                    reassembled, self._rename_map.mapping
                )
            else:
                reassembled = self._rename_map.apply_to_source(reassembled)

        # Shut down the bridge.
        if self._bridge:
            self._bridge.close()
            self._bridge = None

        return PipelineResult(
            code=reassembled,
            explanations=explanations,
            warnings=warnings,
            chunks_processed=len(chunks),
            chunks_failed=failed,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _process_chunk(
        self,
        chunk: Chunk,
        transforms: list[Transform],
        global_ctx: GlobalContext,
        limiter: RateLimiter,
        max_retries: int,
        verify: bool,
        warnings: list[str],
    ) -> str | None:
        """Process a single chunk through all transforms with retry logic."""
        current_code = chunk.source

        for transform in transforms:
            ctx_text = self._ctx_builder.build_context(
                chunk, global_ctx, self._rename_map.mapping
            )
            conservative = chunk.is_oversized

            for attempt in range(1 + max_retries):
                try:
                    async with limiter:
                        result = await transform.apply(
                            code=current_code,
                            context=ctx_text,
                            conservative=conservative,
                            rename_map=self._rename_map.mapping,
                        )
                except Exception as e:
                    warnings.append(
                        f"Chunk {chunk.index}, {transform.task_name} "
                        f"attempt {attempt + 1} error: {e}"
                    )
                    continue

                # Merge rename map if applicable.
                if result.rename_map:
                    self._rename_map.merge(result.rename_map)

                # Verify.
                if verify and transform.task_name != "explain":
                    vr = self._verify_transform(
                        transform.task_name, current_code, result.code
                    )
                    if not vr:
                        violation_msg = f"Chunk {chunk.index}, {transform.task_name}: verification failed"
                        if attempt < max_retries:
                            warnings.append(f"{violation_msg}, retrying...")
                            continue
                        else:
                            warnings.append(
                                f"{violation_msg}, keeping original"
                            )
                            break

                current_code = result.code
                break

        return current_code

    def _verify_transform(
        self, task: str, original: str, transformed: str
    ) -> bool:
        """Run the appropriate verification for *task*.

        Prefers the Node.js bridge (deep AST comparison) when available,
        falls back to the lightweight tree-sitter verifier otherwise.
        """
        if self._bridge:
            try:
                return self._bridge.verify_ast(original, transformed, task).ok
            except RuntimeError:
                pass  # Fall through to tree-sitter verifier.

        match task:
            case "simplify":
                return self._verifier.verify_simplify(original, transformed).ok
            case "rename":
                return self._verifier.verify_rename(original, transformed).ok
            case "comment":
                return self._verifier.verify_comment(original, transformed).ok
            case _:
                return True

    @staticmethod
    def _reassemble(
        chunks: list[Chunk],
        processed: dict[int, str],
        original_source: str,
    ) -> str:
        """Reassemble processed chunks into full source, preserving gaps."""
        if not chunks:
            return original_source

        parts: list[str] = []

        # Leading content before first chunk.
        first_start = chunks[0].start_byte
        if first_start > 0:
            parts.append(original_source[:first_start])

        for i, chunk in enumerate(chunks):
            parts.append(processed[chunk.index])

            # Gap between this chunk and the next.
            if i + 1 < len(chunks):
                gap = original_source[chunk.end_byte : chunks[i + 1].start_byte]
                parts.append(gap)

        # Trailing content after last chunk.
        last_end = chunks[-1].end_byte
        if last_end < len(original_source):
            parts.append(original_source[last_end:])

        return "".join(parts)
