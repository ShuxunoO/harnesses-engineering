# Long-Running Architecture: Initializer + Coding Agent

This file expands Principle 4. The two-agent split is the pattern Anthropic describes in *Effective Harnesses for Long-Running Agents*.

---

## Why two agents

The defining constraint: each new session starts with no memory of the previous one. The naive response — one agent that "figures out the work, scaffolds, and implements" — fails because:

- Working out *what to build* is a high-bandwidth conversation (the user explains, corrects, clarifies).
- *Implementing* is a low-bandwidth long-running loop (grep, edit, test).
- Folding both into one agent creates startup-protocol bloat, context churn, and unclear failure attribution.

| Agent | Runs | Responsible for | Output |
|---|---|---|---|
| **Initializer** | Once, at project start | Aligning with the user; scaffolding | `init.sh`, `feature_list.json` (or `tests.json`), `progress.txt`, first git commit |
| **Coding** | Every working session | Following the startup protocol; one feature | git commits, updated progress, flipped `passes` |

---

## Initializer agent

### Inputs

- The user's project description (natural language).
- Optionally: an existing codebase, reference material.

### Workflow

1. **Interview the user** (high-bandwidth):
   - What is this app? Who is the user?
   - Which features are MVP? Which are nice-to-have?
   - What stack? How is the dev environment started?
   - How is "done" defined for each feature (acceptance criteria)?
2. **Generate scaffolding files**:
   - `init.sh` — one-shot environment bringup (install deps, start services, run migrations).
   - `feature_list.json` — atomic features, each with `steps` and `passes: false`.
   - `progress.txt` — initial narrative: project background, current state, suggested next step.
   - `CLAUDE.md` (or system prompt) — startup protocol the coding agent will obey.
3. **Run a baseline E2E** to confirm `init.sh` works and a "hello world" path passes. Skipping this hands the coding agent a broken environment.
4. **First git commit** — the scaffolding becomes the starting state.

### Initializer tool set

- `Read`, `Write`, `Edit`, `Glob`, `Grep`.
- `Bash` (required, for testing `init.sh`).
- `AskUserQuestion` (used heavily during alignment).
- Optional: `WebFetch` (look up library docs).

### Done criterion

`feature_list.json` is written, `init.sh` runs cleanly, baseline E2E is green, and there is a first git commit. The initializer then exits.

---

## Coding agent

### Startup protocol (every session, no exceptions)

Encoded in `CLAUDE.md` / system prompt:

```
1. pwd                                           # confirm working directory
2. git log --oneline -20                         # what was done recently
3. cat progress.txt                              # narrative state
4. jq '...' feature_list.json                    # pick highest-priority passes:false
5. ./init.sh                                     # bring up the dev environment
6. ./run_e2e.sh --smoke                          # baseline / smoke test
7. then start work on the chosen feature
```

**Hard rule.** If step 6 fails, do *not* continue editing. Either debug the environment or `git reset --hard` to the last known-green commit. Editing on a broken state is the canonical anti-pattern.

### Working loop

1. Read the chosen feature's `steps`.
2. Implement.
3. Lint / type-check (the `PostToolUse` hook fires automatically).
4. Run the `steps` (Playwright / Puppeteer / Bash / pytest, depending on stack).
5. All pass → flip `passes: true`, write `last_verified_commit` = current HEAD.
6. Otherwise → revise and repeat.
7. After N attempts without progress, do not force it. Write the blocker into `progress.txt` and hand off.

### Wrap-up (after a feature passes)

```
1. git add .
2. git commit -m "feat(<area>): <what>. why: <reason>"
3. Append to progress.txt:
   ## Session N (<date>)
   - Implemented: <feature id + summary>
   - Approach: <why this way; tradeoffs>
   - Next: <what should come next>
4. Exit. Do not start another feature.
```

The exit rule is the increment principle in concrete form.

### Coding agent tool set

- `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`.
- Optional: `Agent` (dispatch a reviewer or tester subagent).
- Optional: Playwright MCP for visual verification.

---

## File responsibilities

```
project_root/
├── CLAUDE.md            # startup protocol + project domain knowledge
├── init.sh              # one-shot environment bringup
├── run_e2e.sh           # E2E entry point (--smoke for fast loop)
├── feature_list.json    # structured task list (immutable steps)
├── progress.txt         # narrative log (append-only)
├── .git/                # state-recovery mechanism
└── src/                 # actual code
```

| File | Written by | Modified by | Nature |
|---|---|---|---|
| `CLAUDE.md` | Initializer | Rarely (only on project pivot) | Contract |
| `feature_list.json` | Initializer | Coding agent flips `passes` and writes `last_verified_commit` only — not `id`, `description`, or `steps` | Contract |
| `progress.txt` | Initializer (seed) | Coding agent appends every session | Narrative log |
| `init.sh` | Initializer | Updated when deps change | Tool |
| Git history | Coding agent commits per session | Never rewritten | Source of truth |

---

## Session walkthrough

Imagine session 5 of an app build:

```
[Coding agent starts]
> pwd
/home/user/myapp
> git log --oneline -20
abc123 feat(auth): password reset flow. why: feature_list demanded
def456 feat(auth): login form. why: ...
...
> tail -50 progress.txt
[Reads: login + password reset done; next is feat-007 = avatar upload]
> jq '.[] | select(.passes==false) | .id' feature_list.json | head -1
"feat-007"
> ./init.sh
[Dev server up]
> ./run_e2e.sh --smoke
✓ login flow
✓ password reset
[2 passed, 0 failed]
[Environment green, start feat-007]

... [implementation: edit, lint, run steps, revise] ...

[All steps pass]
> jq '.[6].passes = true | .[6].last_verified_commit = "$(git rev-parse HEAD)"' ...
> echo "## Session 5 (2026-05-09)
  - Implemented feat-007 (avatar upload).
  - Approach: multer for upload, S3 for storage. Picked multer
    because it is the standard and the reinvention surface is
    large.
  - Next: feat-008 (avatar crop UI)" >> progress.txt
> git add . && git commit -m "feat(profile): avatar upload via multer + S3. why: feat-007"
[Exit]
```

When session 6 starts, the new agent reads the git log and progress, sees avatar upload landed, and picks up at the crop UI. The handoff works because the state lives on disk, not in the conversation.

---

## Common failure modes and remedies

| Failure | Signal | Remedy |
|---|---|---|
| Coding agent skips the startup protocol | Edits begin without `git log` | Make the protocol the first lines of `CLAUDE.md` in capitals; consider injecting it via a `SessionStart` hook |
| Agent edits `feature_list.json` `steps` | Diff shows `steps` array changed | `PreToolUse` hook on `feature_list.json` blocks any change other than `passes` and `last_verified_commit` |
| Baseline keeps failing, agent keeps editing | E2E smoke fails but `Edit` calls continue | Step 6 of the protocol must say "if baseline fails, exit and report" |
| `progress.txt` becomes a flat to-do list | Several sessions of bullet points without reasoning | Provide a template in `CLAUDE.md`: "what was done, why, what's next" |
| Multiple features per session | One commit touches several `passes` flips | Protocol says "max one feature per session"; commit hook can verify only one `passes` flipped |

---

## When *not* to use this architecture

- Single-shot tasks within a few dozen tool calls.
- One session, no cross-session resumption.
- Exploratory work where requirements aren't yet stable.

For these, run a single agent. The two-agent pattern carries setup overhead; using it for a 30-minute task is over-engineering.

**Quick decision rule.**

| Expected duration | Architecture |
|---|---|
| < 1 hour | Single agent |
| 1 hour – 1 day | Single agent + `progress.txt` + git |
| > 1 day, multiple sessions | Initializer + coding agent |
