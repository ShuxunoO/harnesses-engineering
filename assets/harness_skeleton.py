"""
Minimum-compliant Harness Skeleton (Python / Claude Agent SDK)
==============================================================

A correct-by-default starting point. Encodes the seven principles:

  1. Tool whitelist (Principle 7)
  2. PostToolUse auto-lint (Principle 5)
  3. Specialized read-only subagent (Principle 3)
  4. Startup protocol enforced via system_prompt (Principle 4)
  5. permission_mode is not acceptEdits by default (Principle 7)

Dependencies:
  pip install claude-agent-sdk

Usage:
  python harness.py "your task here"
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    HookMatcher,
    AgentDefinition,
)


# =============================================================================
# Principle 7: tool whitelist
# =============================================================================

ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash",
    "Agent",  # dispatch subagents
]


# =============================================================================
# Principle 5: PostToolUse auto-lint (rules-based feedback layer)
# =============================================================================

async def lint_after_edit(input_data, tool_use_id, context):
    """
    After Edit / Write, run the relevant linter / type-checker and feed errors
    back to the agent. Cheapest possible feedback layer — the agent sees
    problems immediately.
    """
    file_path = input_data.get("tool_input", {}).get("file_path", "")

    if not file_path or not Path(file_path).exists():
        return {}

    feedback_chunks = []

    # TypeScript / TSX
    if file_path.endswith((".ts", ".tsx")):
        result = subprocess.run(
            ["pnpm", "tsc", "--noEmit"],
            capture_output=True, text=True, cwd=Path(file_path).parent,
        )
        if result.returncode != 0:
            feedback_chunks.append(f"TypeScript errors:\n{result.stdout}\n{result.stderr}")

    # Python
    if file_path.endswith(".py"):
        result = subprocess.run(
            ["ruff", "check", file_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            feedback_chunks.append(f"Ruff:\n{result.stdout}")

    if feedback_chunks:
        return {"feedback": "\n\n".join(feedback_chunks)}
    return {}


# =============================================================================
# Principle 4: PreToolUse contract guard for feature_list.json
# =============================================================================

async def protect_feature_list(input_data, tool_use_id, context):
    """
    feature_list.json's steps / id / description form a contract. The agent may
    only modify `passes` and `last_verified_commit`. This is the simple version
    of the guard; a production version should parse JSON and diff strictly.
    """
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path.endswith("feature_list.json"):
        return {}

    new_str = tool_input.get("new_str", "") or tool_input.get("content", "")
    if "passes" not in new_str and "last_verified_commit" not in new_str:
        return {
            "block": True,
            "reason": (
                "feature_list.json steps/id/description are immutable. "
                "Agent may only flip `passes` and write `last_verified_commit`."
            ),
        }
    return {}


# =============================================================================
# Principle 7: dangerous Bash gate
# =============================================================================

DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "DROP TABLE",
    "DROP DATABASE",
    "TRUNCATE",
    "git push --force",
    "git push -f",
    ":(){ :|:& };:",  # fork bomb
]


async def gate_dangerous_bash(input_data, tool_use_id, context):
    cmd = input_data.get("tool_input", {}).get("command", "")
    for pat in DANGEROUS_PATTERNS:
        if pat in cmd:
            return {
                "block": True,
                "reason": (
                    f"Detected dangerous pattern: `{pat}`. "
                    "Use AskUserQuestion for destructive operations."
                ),
            }
    return {}


# =============================================================================
# Principle 3: specialized read-only subagent
# =============================================================================

CODE_REVIEWER = AgentDefinition(
    description="Read-only code reviewer. Returns issues only.",
    prompt=(
        "You are a senior code reviewer. Review the given files / changes for: "
        "(1) correctness bugs, (2) security issues, (3) style violations. "
        "Return a JSON array of issues: "
        '[{"file": "...", "line": N, "severity": "high|med|low", "issue": "..."}]. '
        "Do NOT fix anything. Do NOT modify any file."
    ),
    tools=["Read", "Glob", "Grep"],
)


# =============================================================================
# Principle 4: startup protocol baked into the system prompt
# =============================================================================

STARTUP_PROTOCOL = """
You are a coding agent for {{PROJECT_NAME}}.

CRITICAL — SESSION START PROTOCOL (run these 6 steps FIRST every session):

  1. `pwd`
  2. `git log --oneline -20`
  3. `cat progress.txt | tail -100`
  4. `jq '[.[] | select(.passes==false)] | sort_by(.priority) | .[0]' feature_list.json`
  5. `./init.sh`
  6. `./run_e2e.sh --smoke`

If step 6 fails — STOP. Report the failure. Do NOT continue editing. Either
git reset to a green commit, or hand off to a human.

WORK LOOP (per feature):

  - Read the feature's `steps` from feature_list.json
  - Implement
  - Run the steps yourself (Playwright / curl / pytest)
  - All pass → flip `passes: true`, write `last_verified_commit`
  - Otherwise → revise, repeat

CONTRACTS YOU MAY NOT VIOLATE:

  - feature_list.json: id/description/steps are immutable.
  - tests/: deleting tests requires AskUserQuestion.
  - One feature per session. Done → commit + update progress.txt + EXIT.

VERIFICATION PRIORITY (high → low):

  1. Lint / type / unit-test exit codes
  2. Visual (screenshots + your own multimodal review)
  3. E2E (the steps from feature_list.json)
  4. LLM-as-judge (only for tone / style / subjective criteria)

If you're tempted to say "should be working" — STOP and check actual test
output. Premature victory declaration is the #1 known failure mode.
"""


# =============================================================================
# Entry point
# =============================================================================

async def main():
    if len(sys.argv) < 2:
        prompt = "Run the session start protocol. Then pick the highest-priority feature with passes=false and implement it."
    else:
        prompt = sys.argv[1]

    options = ClaudeAgentOptions(
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="default",  # Principle 7: do not default to acceptEdits

        system_prompt=STARTUP_PROTOCOL,

        hooks={
            "PreToolUse": [
                HookMatcher(matcher="Edit|Write", hooks=[protect_feature_list]),
                HookMatcher(matcher="Bash", hooks=[gate_dangerous_bash]),
            ],
            "PostToolUse": [
                HookMatcher(matcher="Edit|Write", hooks=[lint_after_edit]),
            ],
        },

        agents={
            "code-reviewer": CODE_REVIEWER,
        },

        # Optional MCP servers
        # mcp_servers={
        #     "playwright": {"command": "npx", "args": ["@playwright/mcp"]},
        # },
    )

    async for msg in query(prompt=prompt, options=options):
        print(msg)


if __name__ == "__main__":
    asyncio.run(main())
