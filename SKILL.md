---
name: harness-engineering
description: Use whenever the user is designing, building, debugging, or auditing a Claude Agent SDK harness, agent loop, or long-running coding agent. Covers the gather-context / take-action / verify-work / repeat loop, tool design, agentic-vs-semantic search, subagents, hooks, permissions, MCP, multi-context-window state (init.sh + feature_list.json + progress notes + git), startup protocols, agent self-verification, incremental progression, and the four-step evaluation method. Trigger this skill even when the word "harness" is not used — common phrases include "agent", "tool set", "subagent", "hooks", "permissions", "MCP", "long-running task", "context window blew up", "agent got stuck", "agent claimed it was done but it wasn't", "feature_list", "CLAUDE.md", "init.sh", "convert this script into an agent", "review my agent code", "should we add a vector DB", "design tool granularity", or "scaffold a long-horizon agent". Encodes Anthropic's published harness-engineering principles from *Effective Harnesses for Long-Running Agents* and *Building Agents with the Claude Agent SDK*.
---

# Harness Engineering

This skill turns Anthropic's published guidance on long-running agents into executable engineering practice. The goal: when you help a user build or fix an agent harness, default to the patterns Anthropic's own teams have validated in production rather than improvising.

**Core idea**: a model is not an agent. The model sets the ceiling on capability, but the *harness* — the loop, tools, context strategy, verification, permissions — determines whether the agent actually delivers on long, ambiguous, real-world tasks.

---

## The agent loop is the first-principles frame

> "Gather context → Take action → Verify work → Repeat."
> — *Building Agents with the Claude Agent SDK*

Every harness decision must map to one of these four phases. If a component does not, it is either redundant or an anti-pattern.

| Phase | Question | Primary harness levers |
|---|---|---|
| Gather context | Can the agent get the right information? | Tool set, file/directory layout, agentic search, subagent isolation |
| Take action | Can the agent turn intent into state changes? | Tool granularity, Bash, code generation, MCP, permissions |
| Verify work | Does the agent know it succeeded? | Rules-based feedback, visual feedback, E2E tests, LLM-as-judge |
| Repeat | Can it stay coherent across many steps and sessions? | Compaction, external state files, git, subagents |

When a question lands, name the phase first. That alone removes most ambiguity.

---

## The seven principles (cheat sheet)

| # | Principle | One-liner |
|---|---|---|
| 1 | Agentic search before semantic search | `grep`, `glob`, `find` are the default. Vector retrieval is a last resort, only after eval data shows agentic search fails. |
| 2 | Few tools, each high-leverage | Tools are verbs, not 1:1 wrappers around API endpoints. Bash plus code generation cover the long tail. |
| 3 | Context is scarce — manage it deliberately | Compaction + external state files + subagent isolation. Anthropic states "compaction isn't sufficient" on its own. |
| 4 | Long-running tasks need a startup protocol | Every session starts by reading state from disk. Use an initializer agent to produce `init.sh`, `feature_list.json` (or `tests.json`), and `progress.txt`. |
| 5 | Every feature must be agent-self-verifiable | Priority: rules-based > visual > E2E > LLM-as-judge. The #1 known failure mode is "premature victory declaration". |
| 6 | Increment, never one-shot | One feature per session; commit, update progress, exit. On a broken state, `git reset` — do not patch on top of decay. |
| 7 | Permissions are a design choice | Whitelist `allowed_tools`. Route irreversible actions through `AskUserQuestion`. |

Full argument and quotes: `references/principles.md`.

---

## How to use this skill in conversation

The flowchart below picks up the most common situations. When one fits, follow the linked steps.

### A. The user wants to start a new agent / harness project

This is high-leverage — early architecture decisions cascade.

1. Establish the task boundary first. Is this a long-running task (multiple sessions, or a single session with dozens of tool calls, or work that spans days)?
   - Yes → use the **initializer + coding agent** two-agent pattern (`references/long-running-architecture.md`).
   - No → a single agent is fine, but principles 1, 2, 3, 7 still apply.
2. Walk `assets/new-harness-checklist.md` to surface gaps.
3. Produce a minimal scaffold from `assets/harness_skeleton.py`, trimmed to the user's stack.
4. Adapt `assets/CLAUDE.md.template` into the project's startup protocol — replace placeholders with real commands, file names, and domain context.

### B. The agent is unstable, stuck, or producing wrong results

Diagnose in this order (Anthropic's four-step evaluation method, see `references/evaluation.md`):

1. **Information access** — can the agent reach the information it needs?
   *Probe*: which search tools is it using? Does the directory structure surface the right files? *Fix*: rename, restructure, or add a domain-specific search verb.
2. **Systematic failures** — does the same kind of error recur?
   *Fix*: encode the rule into a `PreToolUse` hook. Rewriting the prompt to "remind" the model is a gamble; a hook is deterministic.
3. **Self-correction** — when it errs, can it recover?
   *Fix*: hand it more *creative* tools (Bash, code generation), not more narrow APIs.
4. **Regression** — did adding a feature break old cases?
   *Fix*: run a programmatic eval against a real-prompt test set.

If the user starts editing the prompt without running an eval, stop them. No baseline = blind change.

### C. The user asks "should we add a vector DB / semantic search?"

Default answer: **not yet**. Push back with two questions:

- On which specific queries does `grep` / `glob` underperform? Are there numbers?
- Could the directory or file naming be more semantic (names *are* context)?

Move to a retrieval layer only when **all** of the following hold:

- Eval data shows agentic search is below a needed threshold.
- A profiler — not vibes — shows search is the bottleneck.
- The team accepts the opacity, maintenance cost, and debugging difficulty.

Anthropic's stated trade-off: semantic retrieval is "typically faster, but less accurate, harder to maintain, and opaque" (*Building Agents with the Claude Agent SDK*).

### D. The user wants to wrap every API endpoint as a tool

Stop them. Ask:

- Which 3–5 actions does this agent perform *every day*? Make those the dedicated tools — small returns, names the model can pick correctly on first read.
- For the rest, fall back to Bash and code generation. A shell is more powerful than 50 narrow API wrappers.

When the tool count exceeds ~10, treat it as a design alarm. See `references/anti-patterns.md` ("a tool per endpoint").

### E. The user asks how the agent will know it's done

Recommend in this priority order (high to low):

1. **Rules-based** — lint, type-check, regex, unit-test exit codes — wired through a `PostToolUse` hook.
2. **Visual** — Playwright / Puppeteer screenshots, fed back through the model's multimodal input. Mandatory for UI work.
3. **E2E** — the `steps` field in `feature_list.json` (or `tests.json`); the agent runs them and only then flips `passes: true`.
4. **LLM-as-judge** — reserve for tone, style, subjective dimensions. Anthropic calls this "generally not a very robust method, and can have heavy latency tradeoffs."

Why this order: rules-based feedback is deterministic, cheap, low-latency. Climb the ladder only when the lower rung cannot answer the question. See `references/verification.md`.

**Always-on warning**: Anthropic's named #1 failure mode is *premature victory declaration*: "a later agent instance would look around, see that progress had been made, and declare the job done." If the agent reports "complete" without test output in the transcript, treat it as not done.

### F. The task will run more than an hour or span multiple sessions

Go straight to the two-agent pattern (`references/long-running-architecture.md`):

1. **Initializer agent** (one-shot): produces `init.sh`, `feature_list.json`, `progress.txt`, the first git commit.
2. **Coding agent** (every working session): runs the startup protocol, picks one feature, commits, updates progress, exits.

Hard line: without `init.sh`, a structured task file, and git, do not run a long-horizon agent. The official article is explicit that **compaction alone is not sufficient**.

### G. The user wants to push business logic into hooks

Block this. Hooks are the *deterministic* layer. The model does ambiguous reasoning; hooks enforce things you don't want the model to decide. See `references/sdk-cheatsheet.md` for the hooks table.

Common misuses to flag: rewriting tool returns to mislead the model in `PostToolUse`; rewriting the user's prompt in `UserPromptSubmit`; running long blocking work in `SessionStart`.

---

## Anti-pattern signals (interrupt the conversation when seen)

Pull the matching entry from `references/anti-patterns.md` and quote it back to the user.

- "Let the agent build the whole thing in one shot."
- The agent reports "done" but no test output appears in the transcript.
- A vector DB is being added before any profiling of `grep`.
- An 11th tool is being added.
- A long-horizon agent has no progress file or no git history.
- LLM-as-judge is the *primary* evaluator.
- The agent edits or removes existing entries in `feature_list.json` or `tests/`.
- `permission_mode: "acceptEdits"` is set, but no `PostToolUse` audit/verify loop exists.
- Each API endpoint is being wrapped in its own tool.
- A subagent's prompt just forwards the parent agent's prompt with no specialization.

---

## Opening a new harness project — sequence

1. Confirm the task boundary with the user (long-running? single-shot? multi-user? what external systems?).
2. Re-read `references/principles.md` so the seven principles are concrete in your head.
3. Copy `assets/CLAUDE.md.template` to the project's `CLAUDE.md` and substitute placeholders.
4. Copy `assets/feature_list.template.json` to seed the feature list.
5. Copy `assets/harness_skeleton.py` as the SDK entry point; trim what you don't need.
6. Copy `assets/init.sh.template` to set up the dev-server / environment script.
7. Walk `assets/new-harness-checklist.md` line by line.
8. Run a baseline E2E *before* asking the agent to implement anything — confirm the environment is green.

---

## Reference index (`references/`)

Load on demand; reading these in full upfront is unnecessary.

- `references/principles.md` — full argument, examples, and direct quotes for each of the seven principles.
- `references/long-running-architecture.md` — initializer + coding agent pattern, file responsibilities, session lifecycle.
- `references/verification.md` — the four verification strategies, with implementation sketches and upgrade triggers.
- `references/anti-patterns.md` — recognition signals plus a one-paragraph fix for each pattern (quote directly to the user).
- `references/evaluation.md` — the four-step evaluation method, test-set sourcing, regression strategy.
- `references/sdk-cheatsheet.md` — Claude Agent SDK quick reference (tools, hooks, subagents, permissions, MCP).

---

## Asset index (`assets/`)

Drop-in files for the user's project — copy and substitute placeholders.

- `assets/CLAUDE.md.template` — startup protocol plus project system-prompt skeleton.
- `assets/feature_list.template.json` — schema for the structured task list with sample entries.
- `assets/claude-progress.template.txt` — narrative progress-log template.
- `assets/init.sh.template` — idempotent dev-environment bootstrap script.
- `assets/harness_skeleton.py` — minimum-compliant Python entry point for the Claude Agent SDK.
- `assets/post_tool_use_lint_hook.py` — reference `PostToolUse` lint hook implementation.
- `assets/new-harness-checklist.md` — Markdown-checkbox audit for new harnesses.

---

## Source documents

All recommendations trace to:

- *Effective Harnesses for Long-Running Agents* — <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- *Building Agents with the Claude Agent SDK* — <https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk>
- *Prompting best practices — Multi-context-window workflows* — <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>
- *Claude Agent SDK overview* — <https://code.claude.com/docs/en/agent-sdk/overview.md>
- *Hooks reference* — <https://code.claude.com/docs/en/hooks.md>
- *Subagents in the SDK* — <https://code.claude.com/docs/en/agent-sdk/subagents.md>
- *Permissions* — <https://code.claude.com/docs/en/agent-sdk/permissions.md>
- *MCP integration* — <https://code.claude.com/docs/en/agent-sdk/mcp.md>

Direct quotes used in conversations live at the end of `references/principles.md`.
