# Claude Agent SDK Cheat Sheet

A quick reference for the API surface most relevant to harness work. Use this in conversation so you don't have to context-switch to the official docs.

> Full API: <https://code.claude.com/docs/en/agent-sdk/overview.md>

---

## `ClaudeAgentOptions` — top-level configuration

```python
from claude_agent_sdk import (
    query, ClaudeAgentOptions, HookMatcher, AgentDefinition
)

options = ClaudeAgentOptions(
    # === Tool whitelist (Principle 7) ===
    allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep", "Agent"],

    # === Permission mode (Principle 7) ===
    permission_mode="default",
    # default:           prompt user on each sensitive call (use during development)
    # acceptEdits:       auto-accept edits (only after audit hooks are in place)
    # bypassPermissions: fully autonomous (CI / production with full audit)

    # === Hooks (Principle 5) ===
    hooks={
        "PreToolUse": [HookMatcher(matcher="Edit|Write", hooks=[my_pre_hook])],
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[my_post_hook])],
        # Also: UserPromptSubmit, SessionStart, SessionEnd, Stop
    },

    # === Subagents (Principle 3) ===
    agents={
        "code-reviewer": AgentDefinition(
            description="Read-only code review.",
            prompt="...",
            tools=["Read", "Glob", "Grep"],
        ),
    },

    # === MCP servers ===
    mcp_servers={
        "playwright": {"command": "npx", "args": ["@playwright/mcp"]},
    },

    # === System prompt ===
    system_prompt="...",  # alternatively, place in CLAUDE.md
)
```

---

## Hooks

| Hook | When it fires | Use for | Don't use for |
|---|---|---|---|
| `PreToolUse` | Before a tool call | Validate args, block dangerous calls, inject context | Implementing business logic |
| `PostToolUse` | After a tool call | Audit, run lint / format, trigger tests, give feedback | Rewriting tool returns to mislead the model |
| `UserPromptSubmit` | When the user submits | Inject project context, classify intent | Rewriting the user's prompt |
| `SessionStart` | At session open | Load state files, run health checks, inject startup hints | Long blocking work |
| `SessionEnd` | At session close | Persist state, clean up | — |
| `Stop` | When the agent loop stops | Wrap-up (commit, notify) | Restarting the loop |

### Hook function signature

```python
async def my_hook(input_data, tool_use_id, context):
    """
    input_data: dict — includes tool_input (Pre/Post), prompt (UserPromptSubmit), etc.
    tool_use_id: str — unique ID
    context: agent context

    Return values:
      - {} or {"continue": True} — proceed
      - {"block": True, "reason": "..."} — block (PreToolUse)
      - {"feedback": "..."} — inject info into the next turn (PostToolUse)
    """
    return {}
```

### Matcher patterns

```python
HookMatcher(matcher="Edit|Write", hooks=[...])  # only Edit or Write
HookMatcher(matcher="*", hooks=[...])           # all tools
HookMatcher(matcher="Bash", hooks=[...])        # only Bash
```

### Canonical PostToolUse: auto-lint

See `assets/post_tool_use_lint_hook.py` for the full implementation. Sketch:

```python
async def lint_after_edit(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if file_path.endswith((".ts", ".tsx")):
        result = subprocess.run(["pnpm", "tsc", "--noEmit"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            return {"feedback": f"TypeScript errors:\n{result.stdout}"}
    return {}
```

---

## Subagents

### When to use (any one is enough)

1. **Context isolation** — subtask reads heavy content (scan 100 files for TODOs); the parent only needs the conclusion.
2. **True parallelism** — independent subtasks running concurrently.
3. **Specialization** — distinct system-prompt role (`code-reviewer`, `test-writer`, `designer`).

### When *not* to use

- A subagent whose `prompt` just forwards the parent prompt — delete it (anti-pattern AP-9).
- A task that's one or two steps — do it directly.

### `AgentDefinition`

```python
AgentDefinition(
    description="One sentence describing what this agent does (the parent reads this when scheduling)",
    prompt="""You are role X.
    Your goal is Y.
    Output format must be Z (e.g., JSON / structured report).
    You only do W; you do not do V.
    """,
    tools=["Read", "Glob", "Grep"],  # subagent's own whitelist
    # Parent invokes via the Agent tool; "Agent" must be in the parent's allowed_tools
)
```

### Invocation

The parent calls the `Agent` tool:

```
Agent(name="code-reviewer", task="Review the changes in src/auth/", ...)
```

The return is the subagent's final, distilled output — that's where the context isolation pays off.

### Tracing

Subagent messages carry `parent_tool_use_id`. Audit logs must preserve it for traceability.

---

## Permissions

### `allowed_tools` strategy

| Agent role | Recommended tools |
|---|---|
| Code review / read-only | `Read`, `Glob`, `Grep` |
| Code editing | + `Edit`, `Write` |
| Running commands / tests | + `Bash` |
| Dispatching subagents | + `Agent` |
| Browser-based verification | + Playwright MCP tools |
| Payment / mail / database delete | dedicated tool + mandatory `AskUserQuestion` |

### `permission_mode`

| Mode | Behavior | When to use |
|---|---|---|
| `default` | Prompts on each sensitive call | Development, new harness, no audit yet |
| `acceptEdits` | Auto-accepts edits | After audit hooks are in place |
| `bypassPermissions` | Fully autonomous | CI / production with full audit |

**Upgrade path.** `default` → add `PostToolUse` audit → add `PreToolUse` block on dangerous ops → only then `acceptEdits`.

### Sensitive actions: `AskUserQuestion`

Irreversible operations must have a human gate.

```python
# Detect dangerous commands and require explicit confirmation
async def gate_dangerous(input_data, tool_use_id, context):
    cmd = input_data.get("tool_input", {}).get("command", "")
    danger_patterns = ["rm -rf /", "DROP TABLE", "git push --force", "DELETE FROM"]
    if any(p in cmd for p in danger_patterns):
        return {"block": True, "reason": "Use AskUserQuestion for destructive ops"}
    return {}
```

---

## MCP integration

### When to use

- An off-the-shelf MCP server exists (Playwright, GitHub, Linear, Slack) — wire it in.
- Tools to share across agents / projects — MCP is the reuse layer.
- Long-running stateful services (e.g., a browser instance).

### How

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp"],
        },
        "github": {
            "command": "node",
            "args": ["./mcp-servers/github/index.js"],
            "env": {"GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]},
        },
    },
    allowed_tools=[
        # ... built-in tools
        "mcp__playwright__navigate",
        "mcp__playwright__screenshot",
        # MCP tool names: mcp__<server-name>__<tool-name>
    ],
)
```

### Common off-the-shelf MCPs

- **Playwright** — browser automation, screenshots (visual verification).
- **GitHub** — issues, PRs, commits.
- **Filesystem** — cross-process file access.
- **SQLite / Postgres** — database CLIs.

Reference: <https://code.claude.com/docs/en/agent-sdk/mcp.md>

---

## `query()`

```python
async for msg in query(
    prompt="user task here",
    options=options,
):
    print(msg)  # streams agent output, tool calls, tool results
```

### Message types

- `AssistantMessage` — agent text output.
- `ToolUseMessage` — agent invoked a tool.
- `ToolResultMessage` — tool result.
- `SystemMessage` — hook injection or SDK internal.
- `ResultMessage` — final result (cost, duration).

### Resuming a session

```python
session_id = None
async for msg in query(prompt=..., options=options):
    if hasattr(msg, "session_id"):
        session_id = msg.session_id

# Later
options_resume = ClaudeAgentOptions(..., resume=session_id)
async for msg in query(prompt="continue work", options=options_resume):
    ...
```

---

## Common configurations

### Pattern 1: developer-driven harness

```python
ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep", "Agent"],
    permission_mode="default",  # watch the agent during development
    hooks={
        "PostToolUse": [HookMatcher(matcher="Edit|Write",
                                    hooks=[lint_after_edit, audit_log])],
    },
    agents={
        "code-reviewer": AgentDefinition(...),
    },
)
```

### Pattern 2: CI / unattended

```python
ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    permission_mode="bypassPermissions",  # no human, but full hook coverage
    hooks={
        "PreToolUse": [HookMatcher(matcher="Bash",
                                   hooks=[gate_dangerous, audit_cmd])],
        "PostToolUse": [HookMatcher(matcher="*", hooks=[audit_all])],
        "Stop": [HookMatcher(matcher="*", hooks=[notify_slack])],
    },
    system_prompt=open("CLAUDE.md").read(),
)
```

### Pattern 3: long-running, two-agent

See `references/long-running-architecture.md`. Two distinct `ClaudeAgentOptions`:

- Initializer: broad tools, heavy `AskUserQuestion`, runs once.
- Coding: tight whitelist, strict startup protocol, one feature per session.

---

## One-line summary

> Hooks are the deterministic layer; subagents are isolation and specialization; permissions are design, not remediation; MCP is the tool-reuse layer. Configure those four right and SDK usage stays on track.
