# Anti-Patterns: Recognition Signals and Fixes

Each entry below gives **why it's an anti-pattern, the conversational signals that flag it, and a one-paragraph fix to quote back to the user**.

Treat this as a triage sheet — when a signal fires, jump to the entry and respond.

---

## AP-1: "Build the whole thing in one shot"

**Why.** A one-shot run is a single, unverified state change. When something breaks mid-run you can either roll back the whole thing or hand-salvage the wreckage.

**Signals.**

- "Let the agent build this app end-to-end."
- "I'll check it when it finishes."
- "I'll let it run overnight and look at the result tomorrow."
- "Single PR with 30 features."

**Fix.**

> Switch to incremental: one feature per session, then commit, update progress, and exit. Overnight should mean "many sequential sessions, each completing one feature" — not "one session doing many features." Git is your state-recovery mechanism: when a state goes bad, `git reset` to the last green commit. Do not patch on top of decay.

References Principle 6.

---

## AP-2: Premature victory declaration

**Why.** The model has an optimistic bias toward declaring "done." Anthropic names this as a primary failure mode: "a later agent instance would look around, see that progress had been made, and declare the job done."

**Signals.**

- "Implemented X" with no test / build / curl output in the transcript.
- "Should be working", "looks correct", "in theory".
- The user says "the agent said it was done but it's actually broken."
- `passes: true` is written but `last_verified_commit` is empty.

**Fix.**

> Default to disbelieving "complete" until you see test output. Make verification structural: `passes: true` requires a non-null `last_verified_commit`, and the commit must appear in recent `git log`. Add a `PostToolUse` check on writes to the structured task file — if the commit referenced in `last_verified_commit` doesn't exist in git, reject the write.

References Principle 5.

---

## AP-3: Reaching for a vector DB before exhausting `grep`

**Why.** Adds operational burden, opacity, and removes the agent's ability to iterate the search. `grep` is usually adequate; people just haven't really tried.

**Signals.**

- "We'll dump all docs into ChromaDB / Pinecone / pgvector."
- "We need RAG, so..."
- "The agent can't find things — must need embeddings."

**Fix.**

> Pause. Two questions: (1) On which specific queries does `grep` / `glob` underperform? Numbers, not vibes. (2) Could the directory or file naming carry more meaning (names *are* context)? Vector retrieval is the last resort — used only after eval data shows agentic search is below threshold *and* a profiler shows search is the bottleneck. Defer until you have data.

References Principle 1.

---

## AP-4: A tool per API endpoint

**Why.** Selection error rises sharply once tool count exceeds ~10. Imposing the API's shape on the agent is not the same as making the agent effective with that API.

**Signals.**

- "Our API has 47 endpoints, so..."
- "Adding the 12th tool now."
- `searchUsersByName` / `searchUsersByEmail` / `searchUsersByPhone` as separate tools.
- The agent oscillates between near-duplicate tools.

**Fix.**

> Tools are verbs, not endpoint wrappers. Ask: which 3–5 actions does this agent take *every day*? Make those dedicated tools, with small returns and names the model picks correctly on first read. Everything else falls back to Bash and code generation. A shell with a good API client is more powerful than 50 narrow tools.

References Principle 2.

---

## AP-5: Compaction as the only context strategy

**Why.** Compaction is a fallback, not a strategy. Summaries lose detail; in long-running tasks, lost detail makes wrong decisions. Anthropic states: "compaction isn't sufficient" on its own.

**Signals.**

- A long-running task with no `progress.txt` or `feature_list.json`.
- "We use a 200K context model, so we don't worry about it."
- Progress kept in conversation history.
- After compaction, the agent suddenly forgets a key constraint.

**Fix.**

> Long-running tasks need three artifacts: `progress.txt` (narrative), `feature_list.json` or `tests.json` (structured), and git history (code state). These live on disk and are read into each new session by tools — they don't rely on model memory. Compaction is the safety net, not the plan.

References Principle 3.

---

## AP-6: LLM-as-judge as the primary verifier

**Why.** Anthropic's framing: "generally not a very robust method, and can have heavy latency tradeoffs." Regression becomes a coin toss.

**Signals.**

- Feature acceptance is "let another LLM look at it."
- No lint / type-check / E2E — only LLM scoring.
- "We use GPT-4 as judge" as the main test plan.

**Fix.**

> Verification priority is rules-based > visual > E2E > LLM-as-judge. Reserve LLM-as-judge for tone, style, subjective preference. If LLM-as-judge is your main signal today, find what can sink to lint / unit / E2E. Take "is the function correct?" away from the judge; leave it "is the tone consistent?"

References Principle 5.

---

## AP-7: Agent edits or removes existing tests / `feature_list.json` entries

**Why.** The structured task file is a contract. If the agent rewrites `steps`, you've lost the objective measure of "did it work?" Anthropic puts it bluntly: "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."

**Signals.**

- `steps` array shows up in a diff.
- A test file is deleted or commented out.
- "I edited that test, it didn't make sense."
- A failing E2E quietly disappears.

**Fix.**

> Add a `PreToolUse` hook on the structured task file that allows only `passes` and `last_verified_commit` modifications. Add similar protection over `tests/` — deleting a test must go through `AskUserQuestion`. The point is not distrust — it is *structural impossibility*. The agent stops trying after the rule is enforced.

References Principles 4 and 5.

---

## AP-8: No `init.sh` / no progress file at the start of a long-horizon task

**Why.** Each new session has to "guess" how to bring up the environment and where the previous session left off. Small drift each session compounds quickly.

**Signals.**

- Long-running task with no `init.sh`.
- System prompt says "complete features step by step" with no concrete commands.
- Sessions don't continue from where the previous one stopped.

**Fix.**

> Run an initializer agent first. Outputs: `init.sh`, structured task file, `progress.txt`, first git commit. Then the coding agent's startup protocol is fixed: `pwd` → read git log → read progress → read task file → run `init.sh` → run baseline E2E → start work. These six steps are not ceremony; they are the basis for sessions to relay each other.

References Principle 4. See `references/long-running-architecture.md`.

---

## AP-9: Subagents that just forward the parent prompt

**Why.** A subagent without specialization is "fake parallelism" — it costs tokens and adds nothing. Subagents earn their place through *isolation* or *specialization*.

**Signals.**

- The subagent's `prompt` is "do what the user asks."
- The subagent's `tools` list is identical to the parent's.
- Several subagents that look like they overlap.

**Fix.**

> Delete the subagent unless it satisfies one of: (1) context isolation — reads many files, returns only the conclusion; (2) true parallelism — independent subtasks running concurrently; (3) specialization — explicit role with a system prompt (`code-reviewer`, `test-writer`). A subagent that just relays the parent prompt has no reason to exist.

References Principle 3 and the subagents section in `references/sdk-cheatsheet.md`.

---

## AP-10: Permissions wide-open by default

**Why.** Blocklists always leak. Setting `acceptEdits` early hides what you need to see during development.

**Signals.**

- `allowed_tools=*` or unset.
- `permission_mode: "acceptEdits"` with no `PostToolUse` audit.
- "We'll tighten permissions later."

**Fix.**

> Whitelist from day one. MVP = Read + Edit + Write. Bash unlocks once an audit hook ships; MCP network access unlocks once sandbox isolation ships. `acceptEdits` is a *reward* for having a verified audit / verification loop in `PostToolUse` — not a default. Irreversible operations (delete, push, payment, email) route through `AskUserQuestion`.

References Principle 7.

---

## AP-11: Hooks used as a business-logic layer

**Why.** Hooks are the deterministic layer for things you don't want the model to decide. Putting business logic into hooks creates invisible behavior and a debugging nightmare.

**Signals.**

- `PostToolUse` rewrites tool returns to mislead the model.
- `UserPromptSubmit` rewrites the user's words.
- `SessionStart` runs long blocking work.
- Hooks call other LLMs to make subjective calls.

**Fix.**

> Hooks should do four things only: (1) validate input or block dangerous calls (`PreToolUse`); (2) audit, lint, trigger tests (`PostToolUse`); (3) inject project context or classify intent (`UserPromptSubmit` — without rewriting the user's prompt); (4) load state or run health checks (`SessionStart` — non-blocking). Ambiguous reasoning belongs to the model. Deterministic constraints belong to hooks.

See the hooks table in `references/sdk-cheatsheet.md`.

---

## AP-12: Patching on top of a broken state

**Why.** Edits on a broken state make the broken state worse. The agent has no human "stop and reset" instinct — it will keep trying.

**Signals.**

- Baseline E2E fails but the agent keeps editing.
- 50 lint errors and the agent adds more code.
- The agent retries the same change in slight variations and never converges.
- Red-test commits accumulate.

**Fix.**

> Step 6 of the startup protocol is a hard gate: baseline fails → exit and report. Recovery: `git log` for the last green commit, `git reset --hard`, and start the next session from there. Git is a first-class harness component, not just version control. It is the state-recovery mechanism.

References Principle 6.

---

## How to invoke these in conversation

When a signal fires, keep it tight:

> "This looks like a known anti-pattern: [AP-N name]. The reason it fails is [one sentence]. The fix is [one sentence]. This comes from [Principle N], referenced in `references/principles.md`."

Three-part: name, reason, fix. No long lecture.
