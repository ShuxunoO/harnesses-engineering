"""
PostToolUse Lint Hook — automatic lint / type-check feedback layer

This is the canonical implementation of the rules-based feedback layer (Principle 5
in `references/principles.md`). After every Edit / Write, run the appropriate
linter and inject any errors as feedback for the next agent turn — so the agent
sees the problem immediately after introducing it.

Supported:
  - TypeScript / TSX: tsc + eslint
  - JavaScript:        eslint
  - Python:            ruff + mypy
  - Rust:              cargo check
  - Go:                go vet

Usage:
    from post_tool_use_lint_hook import lint_after_edit

    options = ClaudeAgentOptions(
        hooks={
            "PostToolUse": [
                HookMatcher(matcher="Edit|Write", hooks=[lint_after_edit]),
            ],
        },
    )
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Any


# Per-extension command set.
# Each entry: list of (cmd, args, cwd_hint)
# - cmd: binary name
# - args: list[str]; "{file}" is replaced with the actual file path
# - cwd_hint: "file_dir" / "project_root" / None
LINTERS: dict[str, list[tuple[str, list[str], str]]] = {
    ".ts": [
        ("pnpm", ["tsc", "--noEmit"], "project_root"),
        ("pnpm", ["eslint", "{file}"], "project_root"),
    ],
    ".tsx": [
        ("pnpm", ["tsc", "--noEmit"], "project_root"),
        ("pnpm", ["eslint", "{file}"], "project_root"),
    ],
    ".js": [
        ("pnpm", ["eslint", "{file}"], "project_root"),
    ],
    ".jsx": [
        ("pnpm", ["eslint", "{file}"], "project_root"),
    ],
    ".py": [
        ("ruff", ["check", "{file}"], "file_dir"),
        ("mypy", ["{file}"], "file_dir"),
    ],
    ".rs": [
        ("cargo", ["check", "--message-format=short"], "project_root"),
    ],
    ".go": [
        ("go", ["vet", "./..."], "project_root"),
    ],
}


def find_project_root(start: Path) -> Path:
    """Walk up from the file until a project marker is found."""
    cur = start.resolve()
    markers = {".git", "package.json", "Cargo.toml", "pyproject.toml", "go.mod"}
    while cur != cur.parent:
        if any((cur / m).exists() for m in markers):
            return cur
        cur = cur.parent
    return start.parent


async def _run(cmd: list[str], cwd: Path, timeout: float = 30.0) -> tuple[int, str, str]:
    """Run a command with a timeout. Returns (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 124, "", f"Timed out after {timeout}s"
        return proc.returncode, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


async def lint_after_edit(
    input_data: dict[str, Any],
    tool_use_id: str,
    context: Any,
) -> dict[str, Any]:
    """
    Hook entry point. Called after Edit / Write. Runs the relevant linter and,
    if there are issues, injects them as feedback for the next agent turn.

    Returns:
      - {} or {"continue": True}: nothing to flag.
      - {"feedback": "..."}: lint output is injected into the next turn (non-blocking).
    """
    tool_input = input_data.get("tool_input", {}) or {}
    file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        return {}

    file_path = Path(file_path_str)
    if not file_path.exists():
        return {}

    suffix = file_path.suffix
    if suffix not in LINTERS:
        return {}  # No linter configured for this extension; skip.

    proj_root = find_project_root(file_path)

    feedback_chunks: list[str] = []
    for cmd, args_template, cwd_hint in LINTERS[suffix]:
        args = [a.replace("{file}", str(file_path)) for a in args_template]
        cwd = proj_root if cwd_hint == "project_root" else file_path.parent

        returncode, stdout, stderr = await _run([cmd, *args], cwd)

        if returncode == -1:
            # Command not present; skip silently rather than treat as a failure.
            continue
        if returncode != 0:
            output = (stdout + stderr).strip()
            if output:
                feedback_chunks.append(f"`{cmd} {' '.join(args)}` failed:\n{output}")

    if feedback_chunks:
        return {
            "feedback": (
                f"Post-edit checks reported issues for {file_path.name}:\n\n"
                + "\n\n".join(feedback_chunks)
                + "\n\nPlease address these before continuing."
            )
        }
    return {}
