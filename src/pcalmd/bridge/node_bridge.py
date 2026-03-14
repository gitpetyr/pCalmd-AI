"""Python-side bridge to the Node.js AST worker.

Manages a long-running Node.js child process that speaks JSON-line
protocol over stdin/stdout.  Each call sends one JSON line and reads
one JSON line back.  Typical latency per call: ~5 ms.
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from pcalmd.verification.ast_verify import VerifyResult

_WORKER_JS = Path(__file__).parent / "worker.js"


@dataclass
class ScopeBinding:
    """One binding extracted from Babel's scope analysis."""

    name: str
    kind: str  # "var" | "let" | "const" | "param" | "function" | "class" | "import"
    scope_type: str  # "global" | "function" | "block"
    scope_start: int
    scope_end: int
    refs: int  # number of references
    start: int  # identifier start offset
    end: int  # identifier end offset


class NodeBridge:
    """Manages a long-running Node.js AST worker process.

    Usage::

        bridge = NodeBridge()
        try:
            result = bridge.safe_rename(code, {"_0x1a": "userName"})
        finally:
            bridge.close()

    Or as a context manager::

        with NodeBridge() as bridge:
            result = bridge.safe_rename(code, rename_map)
    """

    def __init__(self) -> None:
        node_modules = _WORKER_JS.parent / "node_modules"
        if not node_modules.is_dir():
            raise RuntimeError(
                f"Node modules not installed. Run: "
                f"cd {_WORKER_JS.parent} && npm install"
            )

        self._id = 0
        self._lock = threading.Lock()
        self._proc = subprocess.Popen(
            ["node", str(_WORKER_JS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )

        # Wait for the "ready" signal.
        ready = self._read_line()
        if ready.get("result") != "ready":
            raise RuntimeError(f"Worker failed to start: {ready}")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> NodeBridge:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_scope(self, code: str) -> list[ScopeBinding]:
        """Extract scope bindings from JavaScript *code*."""
        resp = self._call("extractScope", {"code": code})
        return [
            ScopeBinding(
                name=b["name"],
                kind=b["kind"],
                scope_type=b["scopeType"],
                scope_start=b["scopeStart"],
                scope_end=b["scopeEnd"],
                refs=b["refs"],
                start=b["start"],
                end=b["end"],
            )
            for b in resp["bindings"]
        ]

    def safe_rename(self, code: str, rename_map: dict[str, str]) -> tuple[str, dict[str, str]]:
        """Scope-aware rename using Babel.

        Returns ``(renamed_code, applied_renames)`` where
        *applied_renames* is the subset of *rename_map* that was
        actually applied (some entries may be skipped if the binding
        wasn't found).
        """
        resp = self._call("safeRename", {"code": code, "renameMap": rename_map})
        return resp["code"], resp.get("applied", {})

    def verify_ast(
        self, original: str, transformed: str, mode: str
    ) -> VerifyResult:
        """Deep AST structure verification.

        *mode* is one of ``"simplify"``, ``"rename"``, ``"comment"``.
        """
        resp = self._call("verifyAST", {
            "original": original,
            "transformed": transformed,
            "mode": mode,
        })
        return VerifyResult(ok=resp["ok"], violations=resp.get("violations", []))

    def close(self) -> None:
        """Terminate the worker process."""
        if self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.wait(timeout=5)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(self, method: str, params: dict) -> dict:
        """Send a JSON-line request and read the response."""
        with self._lock:
            self._id += 1
            req_id = self._id
            req = {"id": req_id, "method": method, "params": params}
            self._write_line(req)
            resp = self._read_line()

        if "error" in resp:
            raise RuntimeError(f"Node worker error ({method}): {resp['error']}")

        return resp.get("result", {})

    def _write_line(self, obj: dict) -> None:
        self._proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def _read_line(self) -> dict:
        line = self._proc.stdout.readline()
        if not line:
            stderr = self._proc.stderr.read()
            raise RuntimeError(f"Node worker died. stderr: {stderr}")
        return json.loads(line)
