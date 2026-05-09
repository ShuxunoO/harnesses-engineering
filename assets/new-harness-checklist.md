# New Harness Project — Audit Checklist

Copy this into a PR description, design doc, or issue, and check items off. Anything left unchecked is either a known gap (with a plan) or an anti-pattern.

---

## First principles

- [ ] Every harness component maps to one of: **gather context / take action / verify work / repeat**.
- [ ] Components that don't map have been removed.

---

## Task boundary

- [ ] It's clear whether this is a **long-running** task (multi-session) or a **one-shot** task.
- [ ] Long-running → initializer + coding agent two-agent pattern is in place (`references/long-running-architecture.md`).
- [ ] One-shot → not over-engineered (no `feature_list`, no `init.sh`; just a single agent run).

---

## Tools (Principle 2)

- [ ] Tool count ≤ 10.
- [ ] Each tool maps to a high-frequency, core action.
- [ ] Each tool name is a verb phrase (`searchEmails`, not `EmailAPI`).
- [ ] Each tool's return is paginated / truncated / summarized — no 50 KB blobs.
- [ ] `Bash` is available as a fallback (unless a strong security constraint blocks it).
- [ ] No "one tool per API endpoint" anti-pattern.

---

## Context management (Principle 3)

- [ ] **Compaction**: SDK default; no special config needed.
- [ ] **External state files**: `progress.txt` + `feature_list.json` (or `tests.json`) + git history are all present.
- [ ] **Subagent isolation**: heavy reading is delegated to a read-only subagent.
- [ ] Compaction is not the *only* context strategy.

---

## Agentic search (Principle 1)

- [ ] Agent uses `Grep` / `Glob` / `find` by default.
- [ ] No vector DB has been added without profiling data.
- [ ] Directory layout is semantic (a name reveals the contents).

---

## Startup protocol (Principle 4 — long-running only)

- [ ] `init.sh` exists, is idempotent, self-checks, and is non-interactive.
- [ ] Structured task file is JSON, not Markdown.
- [ ] Each entry has `id`, `description`, `steps`, `passes`, `last_verified_commit`.
- [ ] `progress.txt` has an initial narrative seeded by the initializer.
- [ ] `CLAUDE.md` / system prompt encodes the six-step startup protocol.
- [ ] Baseline E2E was actually run and passed before handing the project to the coding agent.

---

## Verification (Principle 5)

- [ ] Every feature has E2E `steps` the agent can run itself.
- [ ] `PostToolUse` runs lint / type-check.
- [ ] UI / visual work has Playwright MCP attached.
- [ ] LLM-as-judge is **not** the primary verifier.
- [ ] `feature_list.json` `steps` / `id` / `description` are protected by a hook.
- [ ] Deleting a file in `tests/` requires `AskUserQuestion`.

---

## Increment (Principle 6)

- [ ] System prompt / `CLAUDE.md` says explicitly "max one feature per session."
- [ ] After a feature, the agent commits, updates progress, and exits.
- [ ] Git is treated as the state-recovery mechanism (broken → reset, not patch).
- [ ] No "build the whole thing in one shot" framing.

---

## Permissions (Principle 7)

- [ ] `allowed_tools` is a **whitelist** (precise list), not a blocklist.
- [ ] `permission_mode` is `default` during development.
- [ ] Irreversible operations (database delete, push, payment, mail) go through `AskUserQuestion`.
- [ ] Dangerous Bash commands are intercepted in `PreToolUse`.
- [ ] `acceptEdits` is *only* enabled after audit hooks are in place.

---

## Hooks (Principles 5 and 7)

- [ ] `PreToolUse`: validate / block dangerous ops / inject context.
- [ ] `PostToolUse`: audit / lint / feedback.
- [ ] `SessionStart`: load state files / health check.
- [ ] Hooks do **not** implement business logic, rewrite tool returns, or rewrite user prompts.

---

## Subagents

- [ ] Each subagent has an explicit system-prompt role.
- [ ] Each subagent satisfies one of: context isolation, true parallelism, specialization.
- [ ] No subagent merely forwards the parent prompt.
- [ ] Subagent tool whitelists are **stricter** than the parent's (especially read-only reviewers).
- [ ] Audit logs preserve `parent_tool_use_id`.

---

## Evaluation (`references/evaluation.md`)

- [ ] Test set is drawn from real user prompts, not developer intuition.
- [ ] Full regression runs in under 30 minutes (parallelize otherwise).
- [ ] Each case has a machine-checkable expected outcome.
- [ ] Regression is run before / after every prompt, tool, or hook change.
- [ ] LLM-as-judge is **not** the main regression signal.

---

## Security

- [ ] Secrets / API keys are not in prompts or in the repo (env vars only).
- [ ] Files the agent should not read are excluded (`.gitignore` + whitelist).
- [ ] Sandbox / container isolation has been considered (especially when Bash is open).

---

## Pass criterion

When every box is checked, the harness:

- Relays cleanly across sessions on long-running tasks.
- Has a small, high-leverage tool set with low selection error.
- Catches errors with feedback rather than silently declaring victory.
- Has structural guards against the named anti-patterns.
- Has an evaluation loop, so changes are no longer a gamble.

**Anything unchecked must be called out explicitly in the PR / design doc** — either with a follow-up plan, or with an explicit acceptance of the trade-off.
