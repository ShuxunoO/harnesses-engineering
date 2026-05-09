# Verification: Four Strategies, Highest to Lowest Priority

This file expands Principle 5. The order matters: lift to the next layer only when the current one cannot answer the question.

---

## Priority table

| Priority | Strategy | Best for | Speed | Cost | Reliability |
|---|---|---|---|---|---|
| 1 | Rules-based (lint / type / regex / exit code) | Code correctness, format | ms | $0 | High (deterministic) |
| 2 | Visual (screenshots + multimodal review) | UI / layout / visual format | seconds | low | Medium |
| 3 | E2E test (user-interaction sequence) | Functional correctness, flow | tens of seconds | low | High |
| 4 | LLM-as-judge | Tone, style, subjective preference | seconds–minutes | higher | Unstable |

---

## 1. Rules-based feedback (default)

The most under-used verification layer. If a linter can answer the question, do not call an LLM.

### Sources of rules

- Compilers and type checkers (`tsc`, `mypy`, `cargo check`).
- Linters (`eslint`, `ruff`, `clippy`).
- Formatters (`prettier`, `black`, `rustfmt`) — divergence becomes an error.
- Unit-test exit codes.
- Custom regex / AST checks (project-specific naming conventions, banned APIs, etc.).

### Wire-up: `PostToolUse` hook

```python
async def lint_after_edit(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "")

    if file_path.endswith((".ts", ".tsx")):
        result = subprocess.run(
            ["pnpm", "tsc", "--noEmit", file_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return {
                "feedback": f"TypeScript errors:\n{result.stdout}\n{result.stderr}",
                "block": False,  # don't block; feed back into next turn
            }
    return {}
```

### Tech-stack choice as verification choice

- TypeScript over plain JavaScript: a free typed-feedback layer.
- Rust over C: the borrow checker is deterministic feedback.
- Pydantic / dataclasses over raw dicts: the model has shape constraints.

A stack with strong rules-based feedback is effectively a free verification layer. This is an under-counted advantage when picking technology.

### Anti-examples

- "We use plain JS to avoid type-fix overhead." You're trading a free verification layer for nothing.
- Lint relaxed to warnings only — that throws away the layer.

---

## 2. Visual feedback

Mandatory for any UI / layout / visual-format work. The model cannot improve what it cannot see.

### Wire-up

- **Playwright MCP** — the recommended path.
- **Puppeteer** — fine if you wrap it.
- **Storybook + screenshots** — for component libraries.

### Workflow

```
1. Agent edits UI code.
2. PostToolUse fires; dev server is running.
3. Playwright runs the per-feature screenshot script.
4. Screenshot paths are returned in the tool result.
5. Agent reads the screenshots multimodally; compares against expectation
   (and any baseline images for diff).
6. If wrong, iterate.
```

### Where it helps

- "Login page should look centered" — text inspection cannot answer this.
- "Submit button is hidden behind the modal" — an E2E might still pass technically but the UX is broken.
- Email / PDF / report layout.

### Anti-examples

- Editing UI without screenshot tooling — typing blind.
- Capturing screenshots but not feeding them back to the model — the verification never happens.

---

## 3. E2E tests

The user-interaction sequence. Every feature in the structured task file should have these.

### Schema (see `assets/feature_list.template.json`)

```json
{
  "id": "feat-001",
  "description": "New Chat button creates a new conversation",
  "steps": [
    "Navigate to the home view",
    "Click the 'New Chat' button",
    "Verify a new conversation is created",
    "Confirm the chat area shows the welcome state",
    "Confirm the conversation appears in the sidebar"
  ],
  "passes": false,
  "last_verified_commit": null
}
```

### Implementation

- **Playwright / Cypress / Puppeteer** for browser flows.
- **Bash + curl** for API flows.
- **pytest / vitest** for server-side flows.

The agent runs the steps, reads the result, and only then flips `passes`. A human flipping `passes` defeats the principle.

### Hard rule: `steps` are immutable

Once written, `steps`, `id`, and `description` are not editable by the agent. Only `passes` and `last_verified_commit` may change. Anthropic's instruction in the source article: "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."

Enforce structurally with a `PreToolUse` hook:

```python
async def protect_feature_list(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if file_path.endswith("feature_list.json"):
        new_content = input_data["tool_input"].get("content", "")
        if not _diff_only_touches_pass_fields(new_content):
            return {"block": True, "reason": "feature_list steps are immutable"}
    return {}
```

### Anti-examples

- Features as Markdown bullets without `steps` — the agent has no objective "done" criterion.
- `steps` like "feature works" — too vague to support `passes: true`.
- Agent silently deletes a failing step. This is a contract violation; a hook must prevent it.

---

## 4. LLM-as-judge (last resort)

Anthropic's framing: "generally not a very robust method, and can have heavy latency tradeoffs."

### Where it fits

- **Tone consistency.** "Is this customer reply polite and on-brand?"
- **Style.** "Is this copy too formal?"
- **Subjective preference.** "Which headline is more engaging?"
- **Creative evaluation.** "Is this title appealing?"

### Where it does not fit

- Functional correctness ("is this code right?") — use unit / E2E.
- Format consistency — use lint / regex.
- Data correctness — use schema validation.

### Implementation

- A separate, read-only judge subagent. Explicit scoring rubric in its system prompt.
- The judge produces verdict + reasoning; it does *not* modify the agent's output.
- Sample multiple times and average — single judgments are unstable.
- Maintain a small ground-truth set with human ratings; check the judge against humans periodically to detect drift.

### Anti-examples

- LLM-as-judge as the only verifier — regression becomes a coin toss.
- The judge also edits — it scores its own work higher.
- No human calibration — the judge can drift silently.

---

## When to climb a level

- **Rules-based → Visual.** When "code is correct but the UX is wrong" bugs appear.
- **Visual → E2E.** When "single page looks fine but the cross-page flow is broken" bugs appear.
- **E2E → LLM-as-judge.** When E2E proves the function works but users say "the tone is off."

This climb works in reverse too. If a project leans heavily on LLM-as-judge today, find what can sink to a lower layer.

---

## Example: a chat application's verification stack

| Layer | What it checks | Trigger |
|---|---|---|
| Lint / TS | Code correct | `PostToolUse(Edit\|Write)` |
| Vitest | Utility correctness | `PostToolUse(Bash)` after edits in `src/utils/` |
| Playwright E2E | Login, send, receive flows | Agent runs explicitly when wrapping a feature |
| Playwright screenshots | UI visuals | Captured during E2E; the agent reads them |
| LLM-judge | Customer-bot reply tone | Run once before flipping `passes` for the chatbot feature |

For each layer, ask: "if only this layer remained, what would I still be able to guarantee?" The more concrete the answer, the more the layer earns its place.
