"""Prompt templates for JavaScript deobfuscation transform tasks."""

from __future__ import annotations

SYSTEM_PROMPT = """You are a JavaScript deobfuscation expert. You receive obfuscated or poorly-readable JavaScript code and improve its readability.

CRITICAL RULES:
1. Preserve the EXACT behavior of the code - do not change what it does
2. Only modify what you are specifically asked to modify
3. Return ONLY the modified code, no explanations or markdown fences
4. If unsure about a change, leave the code as-is"""

SIMPLIFY_PROMPT = """Simplify the following JavaScript code by:
- Removing dead code (unreachable branches, unused variables)
- Folding constant expressions (e.g., 1 + 2 \u2192 3)
- Simplifying redundant control flow (e.g., if(true){{...}} \u2192 ...)
- Removing no-op statements
- Unwrapping unnecessary IIFE wrappers

{context}

CODE TO SIMPLIFY:
```javascript
{code}
```

Return ONLY the simplified JavaScript code. Preserve all functional behavior."""

RENAME_PROMPT = """Rename the obfuscated variables/functions in the following JavaScript code to meaningful names.

RULES:
- Infer purpose from usage patterns, string literals, API calls, and context
- Use camelCase for variables/functions, PascalCase for classes
- Do NOT rename imported/external API names
- Each renamed identifier must be unique
- Return ONLY the renamed code

{context}

EXISTING RENAMES (use these consistently):
{rename_map}

CODE TO RENAME:
```javascript
{code}
```

After the code, on a new line, output a JSON rename map:
RENAME_MAP: {{"old_name": "new_name", ...}}"""

COMMENT_PROMPT = """Add concise inline comments to explain the following JavaScript code.

RULES:
- Add comments that explain WHAT the code does and WHY, not HOW
- Focus on non-obvious logic, magic numbers, and complex expressions
- Do NOT modify the code itself - only add comments
- Use // for single-line comments
- Be concise - one comment per logical block

{context}

CODE TO COMMENT:
```javascript
{code}
```

Return ONLY the commented JavaScript code."""

EXPLAIN_PROMPT = """Explain what the following JavaScript code does.

Provide:
1. A one-paragraph summary
2. A bullet-point list of key behaviors
3. Any notable patterns or techniques used

{context}

CODE TO EXPLAIN:
```javascript
{code}
```"""

# Conservative variants for oversized chunks
CONSERVATIVE_PREFIX = """IMPORTANT: This is a large code section. Apply MINIMAL changes only.
When in doubt, leave the code unchanged. Only make changes you are highly confident about.

"""

# Task name -> prompt template mapping.
_TASK_PROMPTS: dict[str, str] = {
    "simplify": SIMPLIFY_PROMPT,
    "rename": RENAME_PROMPT,
    "comment": COMMENT_PROMPT,
    "explain": EXPLAIN_PROMPT,
}


def build_prompt(
    task: str,
    code: str,
    context: str = "",
    rename_map: dict[str, str] | None = None,
    conservative: bool = False,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the given task.

    Parameters
    ----------
    task:
        One of ``"simplify"``, ``"rename"``, ``"comment"``, ``"explain"``.
    code:
        The JavaScript source to transform.
    context:
        Optional surrounding-code context for the AI to consider.
    rename_map:
        Existing old->new name mappings (only used by the rename task).
    conservative:
        When *True*, prepend a conservative-mode prefix instructing
        the model to apply minimal changes only.

    Returns
    -------
    tuple[str, str]
        ``(system_message, user_message)`` ready for the AI provider.

    Raises
    ------
    ValueError
        If *task* is not one of the recognised transform tasks.
    """
    template = _TASK_PROMPTS.get(task)
    if template is None:
        raise ValueError(
            f"Unknown task {task!r}. Expected one of: {', '.join(_TASK_PROMPTS)}"
        )

    # Build format kwargs common to all templates.
    fmt: dict[str, str] = {
        "code": code,
        "context": context,
    }

    # The rename template has an extra placeholder.
    if task == "rename":
        if rename_map:
            import json

            fmt["rename_map"] = json.dumps(rename_map, indent=2)
        else:
            fmt["rename_map"] = "{}"

    user_prompt = template.format(**fmt)

    if conservative:
        user_prompt = CONSERVATIVE_PREFIX + user_prompt

    return SYSTEM_PROMPT, user_prompt
