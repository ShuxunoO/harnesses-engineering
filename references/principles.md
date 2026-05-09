# The Seven Principles — Detailed Argument

This file expands the cheat sheet in `SKILL.md`. Each principle is laid out as: **rule, why, how, anti-example, source quote**.

---

## Principle 1 — Agentic search before semantic search

**Rule.** Default to `grep`, `glob`, `find`, `tail`, `head`, `cat` over the file system. Add a vector / semantic retrieval layer only after eval data shows agentic search is below threshold *and* a profiler shows search is the bottleneck.

**Why.**

- Anthropic's own framing: semantic retrieval is "typically faster, but less accurate, harder to maintain, and opaque" (*Building Agents with the Claude Agent SDK*).
- Agentic search is **transparent** — every query and result appears in the tool-use log, so failures are debuggable.
- Agentic search is **iterable by the agent itself**. If the first `grep` misses, it can change keywords, regex, or path. With a vector store the agent can mostly only adjust top-k or threshold, which it usually cannot reason about.
- It avoids a whole stack — embedding model, indexing pipeline, vector DB — and the failure modes that come with it.

**How.**

1. Treat the directory layout as context engineering. A repo organized as `docs/api/auth.md` and `tests/integration/payment/` is already grep-friendly.
2. Wrap the 3–5 truly high-frequency search verbs as small dedicated tools (see Principle 2). Do *not* wrap "search" as a vector lookup.
3. When a user reports "the agent can't find X," start with the directory layout, then the search tactic, then — only if those don't explain it — consider retrieval.

**Anti-example.**

- Adding a vector DB in week one because "we'll need RAG eventually."
- Hearing "the agent answers wrongly" and jumping to "add semantic search" without checking which queries failed.
- Acceptable case: six months in, eval data shows agentic search at <50% accuracy on a category of queries, semantic retrieval tested at >80% on the same set, and the team is willing to maintain the pipeline.

---

## Principle 2 — Few tools, each high-leverage

**Rule.** Tools are the agent's verbs. Each tool must:

- (a) be a high-frequency, core action in this domain,
- (b) return output small enough not to pollute context, and
- (c) have a name and signature the model can pick correctly on first read.

**Why.**

- Selection error rises with list length. Once tools exceed roughly ten, expect the model to confuse near-duplicates.
- Every tool description spends context that could otherwise hold reasoning or data.
- Near-duplicate tools (e.g., `searchUsersByName` and `searchUsersByEmail`) cause the model to ping-pong between them.

**How.**

Three categories of tools, per Anthropic guidance:

1. **API-based** (e.g., `fetchInbox`, `searchEmails`) — the dedicated verbs for the main workflow.
2. **Bash / scripting** — the most undervalued tool. A shell makes the agent vastly more capable than 50 narrow API wrappers.
3. **Code generation** — let the agent compose a Python script for "read 100 JSON files and aggregate." Better than a bespoke aggregation tool.

Heuristics:

- 5–8 dedicated tools is healthy. Past 10, redesign.
- Always include Bash unless a security constraint blocks it.
- Name tools as verb phrases (`fetchInbox`, not `InboxAPI`).
- Tools must paginate / truncate / summarize. Never return 50 KB of raw JSON.

**Anti-example.**

- "Our company API has 47 endpoints, so we need 47 tools." This forces the API's shape onto the agent.
- `getUserById`, `getUserByEmail`, `getUserByPhone`, `getUserByUsername` — collapse to a single `findUser(query, by)`, or let the agent run SQL via Bash.
- Healthy: three tools — `searchEmails(query)`, `readEmail(id)`, `composeAndSend(...)` — plus Bash and code generation.

---

## Principle 3 — Context is scarce; manage it deliberately

**Rule.** A harness must run all three of these mechanisms; one is not enough.

1. **Compaction** — automatic summarization near the context limit (built in to the SDK). Anthropic states: "compaction isn't sufficient" on its own.
2. **External state files** — `progress.txt` (narrative), `feature_list.json` or `tests.json` (structured requirements), git history (code state). These are the source of truth, *not* the conversation.
3. **Subagent isolation** — offload "read 100 files and summarize" to a subagent so the parent context only sees the subagent's distilled output.

**Why.**

- Context is finite, tokens cost money, and the model's attention dilutes as the window grows.
- The defining constraint of long-running agents (*Effective Harnesses for Long-Running Agents*): "each new session begins with no memory of what came before."
- Relying only on compaction means betting on summary quality. Summaries lose detail; lost detail leads to wrong decisions.
- External files are deterministic — they don't get "forgotten" and tools can read or write them precisely.

**How.**

- Use plain text or Markdown for narrative progress so a human can review it.
- Use JSON for structured requirements. Anthropic's reasoning: "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files."
- Use git for code state. Commit messages encode the *why*.
- Outsource heavy reading to subagents (see `references/sdk-cheatsheet.md`).

**Hard test.** Task spans multiple sessions → external state files are mandatory. If they don't exist, do not run a long-horizon agent.

**Anti-example.**

- "We have a 200K context window, so we don't need to manage context." Long enough tasks blow through any window, and attention degrades over long inputs.
- Putting progress into the conversation history "so the model remembers it" — the next session has none of it.
- Storing the feature list as a Markdown checklist — the model treats it as an editable document and rewrites it for "polish."

---

## Principle 4 — Long-running tasks need a startup protocol

**Rule.** Every long-running session starts with a fixed sequence:

1. Confirm the working directory (`pwd`).
2. Read git log and `progress.txt` to understand recent work.
3. Read the structured task file (`feature_list.json` / `tests.json`) and pick the highest-priority unfinished item.
4. Run `init.sh` to bring the dev environment up.
5. Run a baseline / smoke E2E to confirm the environment is green.
6. *Then* start implementation.

The official article describes the same idea in three broad steps ("call pwd," "review progress.txt, tests.json, and the git logs," "manually run through a fundamental integration test before moving on to implementing new features"). The 6-step expansion above is the practical form.

**Why.**

- The defining constraint, again: "each new session begins with no memory of what came before."
- Without a startup protocol the agent guesses, drifts a little, and the drift compounds across sessions.
- The baseline E2E is non-negotiable. It confirms the environment is healthy *before* the agent edits code. Editing code on a broken environment makes the broken state worse.

**How — the two-agent pattern.**

1. **Initializer agent** — runs once, at project start:
   - Aligns requirements with the user.
   - Produces `init.sh`, `feature_list.json` (or `tests.json`), `progress.txt`, the first git commit.
   - Exits.
2. **Coding agent** — every working session:
   - Runs the protocol above without exception.
   - Picks one feature.
   - Commits, updates progress, exits.

Details: `references/long-running-architecture.md`.

**Why JSON, not Markdown, for the structured task file.** Direct quote: "After some experimentation, we landed on using JSON for this, as the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files." Treating the file as a contract requires a format the model treats as data.

**Anti-example.**

- A system prompt that says "complete features step by step" with no concrete startup commands — the agent skips git log and starts editing code.
- A startup protocol with no baseline test — the agent "fixes bugs" on a broken environment and makes it worse.
- A feature list stored as freeform notes — every parse interprets it differently.

---

## Principle 5 — Every feature must be agent-self-verifiable

**Rule.** Anthropic names *premature victory declaration* as a primary failure mode: "a later agent instance would look around, see that progress had been made, and declare the job done." The harness has to force verification through tools.

**Verification priority (high → low).**

1. **Rules-based feedback** — lint, type-check, format, unit-test exit codes — wired through a `PostToolUse` hook.
2. **Visual feedback** — Playwright / Puppeteer screenshots fed back through the model's multimodal input. Mandatory for UI / layout / formatting.
3. **E2E tests** — the `steps` field of each entry in the structured task file. The agent runs the steps itself, and only then flips `passes: true`.
4. **LLM-as-judge** — last resort. Anthropic's framing: "generally not a very robust method, and can have heavy latency tradeoffs." Fine for tone, style, subjective dimensions — not for functional correctness.

**Why this order.**

- Rules-based is deterministic, cheap, low-latency. A `tsc` or `ruff` exit code is a free, perfect signal.
- Visual is critical for UI: text inspection won't catch "the button is hidden behind the modal."
- E2E is the proxy for real user interaction. A user does not care that unit tests pass; they care that "submit" works.
- LLM-as-judge is slow, expensive, and may be wrong itself — but for "is the tone polite?" nothing else can answer.

**How.**

- Wire lint / type-check to `PostToolUse(Edit|Write)` so the agent sees errors immediately. TypeScript's free type-check layer is a real architectural advantage over plain JS.
- For UI work, attach a screenshot tool. The model cannot improve layouts it cannot see.
- For each feature, write `steps` (an ordered user-interaction sequence) and `passes: false` in the structured file. Only the agent flips `passes: true`, and only after running the steps. Record `last_verified_commit`.
- Reserve LLM-as-judge for genuinely subjective axes.

**Hard contract.** Existing `steps` and existing tests are immutable. The official article puts this strongly: "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality." Enforce structurally with a `PreToolUse` hook on the structured file.

**Anti-example.**

- Agent reports "login implemented" but the transcript shows no test output. Treat as not done.
- LLM-as-judge as the only check, "to save time" — regression becomes a coin toss.
- Agent deletes a failing E2E because "it was unreasonable." This is a contract violation; design the harness so it is structurally impossible.

---

## Principle 6 — Increment, never one-shot

**Rule.** Anthropic's own observation: a major failure mode is the agent attempting to do "too much at once." The fix is structural: one feature per session.

- Pick one feature.
- Implement.
- Commit (commit message captures the *why*).
- Update `progress.txt` and flip `passes: true` in the structured file.
- Exit.

Direct quote: "the next iteration of the coding agent was then asked to work on only one feature at a time. This incremental approach turned out to be critical to addressing the agent's tendency to do too much at once."

**Why.**

- A one-shot run is a single, unverified state change. When something breaks, you can't isolate where.
- Incremental + git = every step has an anchor. On regression, `git reset` to the last green commit. Do *not* let the agent patch on top of a broken state.
- One feature is the natural unit of verification — its E2E either passes or fails.

**How.**

- Treat git as a first-class harness component. It is not just version control; it is the state-recovery mechanism.
- The system prompt / `CLAUDE.md` must say "max one feature per session" and treat that as a hard limit.
- Commit-message template: `feat(<area>): <what>; why: <reason>`.
- Progress notes are narrative — what was done, why, what's next — not a flat to-do list.

**Anti-example.**

- "Build all 12 features and commit at the end." Mid-run failure forces either a full reset or hand-salvage.
- The agent edits on top of 50 lint errors. Each new edit drifts further from a buildable state. The right move is `git reset --hard` to a known-green commit.

---

## Principle 7 — Permissions are a design choice, not a remediation

**Rule.** Use `allowed_tools` whitelists from day one. Do not give the agent capabilities it doesn't need for the task.

**Why.**

- Blocklists always leak — the tool you didn't think of becomes the next attack surface.
- Setting `acceptEdits` early masks information you need to see during development (the prompts let you watch what the agent does).
- Irreversible operations (delete, push, payment) must have a human gate. Their failure mode is *real* failure.

**How.**

| Agent role | Recommended `allowed_tools` |
|---|---|
| Read-only analysis / code review | `Read`, `Glob`, `Grep` |
| Code editing | + `Edit`, `Write` |
| Running commands / tests | + `Bash` |
| Dispatching subagents | + `Agent` |
| Browser-based verification | + Playwright MCP tools |

Route sensitive actions (delete a database, push, call a payment API, send mail) through `AskUserQuestion` or disable them.

`permission_mode: "acceptEdits"` is a *reward* for having a working audit / verification loop in `PostToolUse`. It is not a default.

**Anti-example.**

- "We'll set `allowed_tools=*` for now and tighten later." The tightening never happens, and the codebase has already absorbed habits that assume any tool works.
- The agent has DELETE permission with no audit hook — when something goes wrong, no one can tell what was deleted, when, or why.
- Healthy: MVP runs Read + Edit only; Bash unlocks once an audit hook ships; MCP network access unlocks once sandbox isolation ships.

---

## Source quotes (for direct citation in conversation)

| Topic | Quote (excerpt) | Source |
|---|---|---|
| Agent loop | "Gather context → Take action → Verify work → Repeat." | *Building Agents with the Claude Agent SDK* |
| Semantic retrieval trade-offs | "typically faster, but less accurate, harder to maintain, and opaque" | *Building Agents with the Claude Agent SDK* |
| Long-running agent constraint | "each new session begins with no memory of what came before" | *Effective Harnesses for Long-Running Agents* |
| Compaction insufficient | "compaction isn't sufficient" | *Effective Harnesses for Long-Running Agents* |
| LLM-as-judge | "generally not a very robust method, and can have heavy latency tradeoffs" | *Building Agents with the Claude Agent SDK* |
| Premature victory declaration | "a later agent instance would look around, see that progress had been made, and declare the job done" | *Effective Harnesses for Long-Running Agents* |
| JSON over Markdown | "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files" | *Effective Harnesses for Long-Running Agents* |
| Tests are immutable | "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality" | *Effective Harnesses for Long-Running Agents* |
| One feature at a time | "the next iteration of the coding agent was then asked to work on only one feature at a time. This incremental approach turned out to be critical" | *Effective Harnesses for Long-Running Agents* |

The full passages are in the source articles linked from `SKILL.md`.
