#!/usr/bin/env node
/**
 * pCalmd-AI Node.js AST worker.
 *
 * Long-running process that reads JSON-line requests from stdin and writes
 * JSON-line responses to stdout.
 *
 * Protocol (one JSON object per line):
 *   Request:  { "id": 1, "method": "extractScope", "params": { "code": "..." } }
 *   Response: { "id": 1, "result": { ... } }
 *   Error:    { "id": 1, "error": "message" }
 */

"use strict";

const { parse } = require("@babel/parser");
const traverse = require("@babel/traverse").default;
const generate = require("@babel/generator").default;
const recast = require("recast");
const readline = require("readline");

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

/**
 * Extract scope bindings from source code.
 *
 * Returns an array of scope entries.  Each entry describes one binding:
 *   { name, kind, scopeType, scopeStart, scopeEnd, refs }
 *
 * kind:      "var" | "let" | "const" | "param" | "function" | "class" | "import"
 * scopeType: "global" | "function" | "block"
 * refs:      number of references to this binding
 */
function extractScope(params) {
  const { code } = params;
  const ast = parseCode(code);

  const bindings = [];
  const seen = new Set();

  traverse(ast, {
    Scope(path) {
      const scopeNode = path.node;
      const scopeType = path.isProgram()
        ? "global"
        : path.isFunction()
        ? "function"
        : "block";

      const scopeStart = scopeNode.start;
      const scopeEnd = scopeNode.end;

      for (const [name, binding] of Object.entries(path.scope.bindings)) {
        const key = `${name}:${binding.identifier.start}`;
        if (seen.has(key)) continue;
        seen.add(key);

        bindings.push({
          name,
          kind: binding.kind,
          scopeType,
          scopeStart,
          scopeEnd,
          refs: binding.referencePaths.length,
          start: binding.identifier.start,
          end: binding.identifier.end,
        });
      }
    },
  });

  return { bindings };
}

/**
 * Scope-aware rename.
 *
 * Accepts a rename map { oldName: newName } and applies it using Babel's
 * scope.rename(), which only touches actual binding references — never
 * string literals, comments, or property accesses via bracket notation
 * that happen to match.
 *
 * Returns the renamed source code with original formatting preserved
 * (via recast).
 */
function safeRename(params) {
  const { code, renameMap } = params;

  // Use recast for format-preserving output.
  const ast = recast.parse(code, {
    parser: {
      parse(source) {
        return parse(source, {
          sourceType: "unambiguous",
          plugins: ["jsx", "typescript", "decorators"],
          tokens: true,
          ranges: true,
        });
      },
    },
  });

  // We need Babel traverse for scope analysis.  Feed it the recast AST
  // (which is Babel-compatible).
  const applied = {};

  traverse(ast, {
    Scope(path) {
      for (const [oldName, newName] of Object.entries(renameMap)) {
        if (path.scope.hasOwnBinding(oldName)) {
          try {
            path.scope.rename(oldName, newName);
            applied[oldName] = newName;
          } catch {
            // Binding may already have been renamed by a parent scope.
          }
        }
      }
    },
  });

  const output = recast.print(ast).code;
  return { code: output, applied };
}

/**
 * Deep AST structure verification.
 *
 * Modes:
 *   "simplify" — transformed must have ≤ nodes; all function/class names preserved.
 *   "rename"   — AST structure identical (ignoring identifier text).
 *   "comment"  — stripping comments from transformed yields identical AST to original.
 */
function verifyAST(params) {
  const { original, transformed, mode } = params;
  const violations = [];

  const origAST = parseCode(original);
  const transAST = parseCode(transformed);

  switch (mode) {
    case "simplify": {
      const origCount = countNodes(origAST);
      const transCount = countNodes(transAST);
      if (transCount > origCount) {
        violations.push(
          `Node count increased: ${origCount} → ${transCount}`
        );
      }
      const origDecls = collectDeclNames(origAST);
      const transDecls = collectDeclNames(transAST);
      for (const name of origDecls) {
        if (!transDecls.has(name)) {
          violations.push(`Missing declaration: ${name}`);
        }
      }
      break;
    }

    case "rename": {
      const result = compareStructure(origAST.program, transAST.program);
      if (!result.ok) {
        violations.push(...result.violations);
      }
      break;
    }

    case "comment": {
      // Strip comments then compare generated code text directly.
      // This catches value changes (e.g., 1 → 2) that structural
      // comparison would miss.
      removeComments(transAST);
      removeComments(origAST);
      const origCode = generate(origAST, { comments: false }).code;
      const transCode = generate(transAST, { comments: false }).code;
      if (normalizeWS(origCode) !== normalizeWS(transCode)) {
        violations.push("Code was modified beyond adding comments");
      }
      break;
    }

    default:
      violations.push(`Unknown mode: ${mode}`);
  }

  return { ok: violations.length === 0, violations };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseCode(code) {
  return parse(code, {
    sourceType: "unambiguous",
    plugins: ["jsx", "typescript", "decorators"],
    errorRecovery: true,
  });
}

function normalizeWS(s) {
  return s.replace(/\s+/g, " ").trim();
}

function countNodes(ast) {
  let count = 0;
  traverse(ast, {
    enter() {
      count++;
    },
  });
  return count;
}

function collectDeclNames(ast) {
  const names = new Set();
  traverse(ast, {
    FunctionDeclaration(path) {
      if (path.node.id) names.add(path.node.id.name);
    },
    ClassDeclaration(path) {
      if (path.node.id) names.add(path.node.id.name);
    },
  });
  return names;
}

/**
 * Compare two AST nodes structurally, ignoring identifier names.
 * Checks that the tree shape (node types, child count) is identical.
 */
function compareStructure(nodeA, nodeB, path = "root") {
  const violations = [];

  if (nodeA === null && nodeB === null) return { ok: true, violations };
  if (nodeA === null || nodeB === null) {
    violations.push(`${path}: one side is null`);
    return { ok: false, violations };
  }
  if (typeof nodeA !== "object" || typeof nodeB !== "object") {
    return { ok: true, violations };
  }

  if (nodeA.type !== nodeB.type) {
    violations.push(`${path}: type ${nodeA.type} → ${nodeB.type}`);
    return { ok: false, violations };
  }

  // Compare children arrays (body, params, etc.) but skip identifier values.
  const keysToCheck = [
    "body",
    "params",
    "declarations",
    "consequent",
    "alternate",
    "cases",
    "elements",
    "properties",
    "arguments",
    "expressions",
  ];

  for (const key of keysToCheck) {
    const a = nodeA[key];
    const b = nodeB[key];
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) {
        violations.push(
          `${path}.${key}: length ${a.length} → ${b.length}`
        );
        // Don't recurse into mismatched arrays.
        continue;
      }
      for (let i = 0; i < a.length; i++) {
        const sub = compareStructure(a[i], b[i], `${path}.${key}[${i}]`);
        violations.push(...sub.violations);
      }
    }
  }

  return { ok: violations.length === 0, violations };
}

function removeComments(ast) {
  traverse(ast, {
    enter(path) {
      if (path.node.leadingComments) path.node.leadingComments = [];
      if (path.node.trailingComments) path.node.trailingComments = [];
      if (path.node.innerComments) path.node.innerComments = [];
    },
  });
}

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------

const METHODS = {
  extractScope,
  safeRename,
  verifyAST,
};

// ---------------------------------------------------------------------------
// Main loop — read JSON lines from stdin, dispatch, write JSON line to stdout.
// ---------------------------------------------------------------------------

const rl = readline.createInterface({ input: process.stdin });

rl.on("line", (line) => {
  let req;
  try {
    req = JSON.parse(line);
  } catch {
    process.stdout.write(
      JSON.stringify({ id: null, error: "Invalid JSON" }) + "\n"
    );
    return;
  }

  const { id, method, params } = req;
  const fn = METHODS[method];
  if (!fn) {
    process.stdout.write(
      JSON.stringify({ id, error: `Unknown method: ${method}` }) + "\n"
    );
    return;
  }

  try {
    const result = fn(params || {});
    process.stdout.write(JSON.stringify({ id, result }) + "\n");
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ id, error: err.message || String(err) }) + "\n"
    );
  }
});

rl.on("close", () => process.exit(0));

// Signal readiness.
process.stdout.write(JSON.stringify({ id: 0, result: "ready" }) + "\n");
