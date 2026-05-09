# harnesses-engineering

A drop-in [Claude Code](https://code.claude.com) **Skill** that turns Anthropic's published guidance on long-running agents into executable engineering practice. When you ask Claude to design, build, debug, or audit a Claude Agent SDK harness, this skill activates and steers the conversation toward the patterns Anthropic's own teams have validated in production — instead of improvising.

> **Core idea:** a model is not an agent. The model sets the ceiling on capability, but the *harness* — the loop, tools, context strategy, verification, permissions — determines whether the agent actually delivers on long, ambiguous, real-world tasks.

---

## What's in this repo

```
harnesses-engineering/
├── SKILL.md                 # The skill entry point (auto-loaded by Claude Code)
├── references/              # Deep-dive docs, loaded on demand
│   ├── principles.md            # The seven principles, full argument + quotes
│   ├── long-running-architecture.md  # Initializer + coding agent two-agent pattern
│   ├── verification.md          # Four verification strategies and upgrade triggers
│   ├── anti-patterns.md         # Recognition signals + one-paragraph fixes
│   ├── evaluation.md            # Anthropic's four-step evaluation method
│   └── sdk-cheatsheet.md        # Claude Agent SDK quick reference
├── assets/                  # Drop-in templates for new harness projects
│   ├── CLAUDE.md.template
│   ├── feature_list.template.json
│   ├── claude-progress.template.txt
│   ├── init.sh.template
│   ├── harness_skeleton.py
│   ├── post_tool_use_lint_hook.py
│   └── new-harness-checklist.md
├── LICENSE                  # MIT
└── README.md                # You are here
```

---

## The seven principles (cheat sheet)

| # | Principle | One-liner |
|---|---|---|
| 1 | Agentic search before semantic search | `grep`, `glob`, `find` are the default. Vector retrieval is a last resort. |
| 2 | Few tools, each high-leverage | Tools are verbs, not 1:1 wrappers around API endpoints. |
| 3 | Context is scarce — manage it deliberately | Compaction + external state files + subagent isolation. |
| 4 | Long-running tasks need a startup protocol | Every session starts by reading state from disk. |
| 5 | Every feature must be agent-self-verifiable | Rules-based > visual > E2E > LLM-as-judge. |
| 6 | Increment, never one-shot | One feature per session; commit, update progress, exit. |
| 7 | Permissions are a design choice | Whitelist `allowed_tools`. Route irreversible actions through `AskUserQuestion`. |

Full argument and source quotes live in [references/principles.md](references/principles.md).

---

## The agent loop is the first-principles frame

> *Gather context → Take action → Verify work → Repeat.*
> — *Building Agents with the Claude Agent SDK*

| Phase | Question | Primary harness levers |
|---|---|---|
| Gather context | Can the agent get the right information? | Tool set, file/directory layout, agentic search, subagent isolation |
| Take action | Can the agent turn intent into state changes? | Tool granularity, Bash, code generation, MCP, permissions |
| Verify work | Does the agent know it succeeded? | Rules-based feedback, visual feedback, E2E tests, LLM-as-judge |
| Repeat | Can it stay coherent across many steps and sessions? | Compaction, external state files, git, subagents |

Every harness decision must map to one of these four phases. If a component does not, it is either redundant or an anti-pattern.

---

## Install

This repo is structured as a Claude Code skill. Install by symlinking (or cloning) it into your skills directory:

```bash
# User-level install (available in every project)
git clone https://github.com/<your-org>/harnesses-engineering.git \
  ~/.claude/skills/harness-engineering

# OR, project-level install
git clone https://github.com/<your-org>/harnesses-engineering.git \
  ./.claude/skills/harness-engineering
```

Claude Code auto-discovers skills under `.claude/skills/`. Once installed, the skill triggers on phrases like *agent*, *harness*, *tool set*, *subagent*, *hooks*, *permissions*, *MCP*, *long-running task*, *context window blew up*, *agent got stuck*, *feature_list*, *CLAUDE.md*, *init.sh* — full trigger list in [SKILL.md](SKILL.md).

To verify it loaded, ask Claude: *"What does the harness-engineering skill cover?"*

---

## Using the skill

You don't *call* this skill explicitly — you describe what you're doing, and Claude Code auto-loads it when the topic matches. Once loaded, Claude steers the conversation through the flowchart in [SKILL.md](SKILL.md), referencing the deeper documents under `references/` and the templates under `assets/` as needed.

### Step 1 — verify the skill is loaded

After install, in a fresh Claude Code session, ask:

```
What does the harness-engineering skill cover?
```

Claude should describe the seven principles, the four-phase agent loop, and the flowchart. If it gives a generic answer about "harnesses" without referencing this skill, the skill isn't loaded — re-check your install path.

### Step 2 — describe your actual situation

Don't ask abstractly ("how do I build an agent?"). Describe the concrete state you're in. The skill recognizes seven common situations (see flowchart **A–G** below). The clearer your description, the more directly Claude jumps into the right playbook.

| Your situation | What to say | What you get back |
|---|---|---|
| **A.** New project | *"I'm building a long-running agent that does X. Help me scaffold the harness."* | Initializer + coding agent pattern, scaffolded from `assets/`, with placeholders filled. |
| **B.** Agent is misbehaving | *"My agent keeps doing X when it should do Y. Help me debug."* | Anthropic's four-step evaluation: information access → systematic failures → self-correction → regression. |
| **C.** Considering vector DB | *"Should I add semantic search / a vector DB to my agent?"* | Default pushback with the bar you have to clear first (eval data + profiling). |
| **D.** Designing tools | *"I have 15 API endpoints — should I wrap each as a tool?"* | Interrupt + redesign around 3–5 verbs plus Bash. |
| **E.** Verification | *"How will my agent know when it's done?"* | The verification ladder: rules-based → visual → E2E → LLM-as-judge. |
| **F.** Long-horizon work | *"This task will run for hours / span sessions."* | Two-agent pattern with `init.sh`, `feature_list.json`, `progress.txt`, git. |
| **G.** Hook design | *"Should I put this logic in a hook?"* | Hooks are the *deterministic* layer only — block business logic from leaking in. |

### Step 3 — let the skill flag anti-patterns

The skill has a list of red flags ([references/anti-patterns.md](references/anti-patterns.md)) it actively watches for. If you say something like *"let's just let the agent build the whole thing in one shot"* or *"the agent says it's done"* without showing test output, expect Claude to interrupt and quote the anti-pattern back at you. That's working as intended — it's the skill's job to challenge those moves.

### Step 4 — pull templates from `assets/` when scaffolding

When Claude recommends a template, it points at a path under `assets/`. You can either:

- Let Claude copy and customize it for you (it'll substitute placeholders based on what you've described).
- Run the bootstrap commands in the [next section](#bootstrapping-a-new-harness-project) yourself.

### Example session — bootstrapping a new harness

```
You: I want to build a Claude agent that audits TypeScript codebases for unused
     exports. Each run will likely process thousands of files and take ~30 min.
     How should I structure the harness?

Claude: [skill loads — recognizes long-running task, situation A + F]
        Two questions before I scaffold:
        1. Will this run as one session, or be resumable across sessions?
        2. What's the verification signal — does "unused export" have a
           deterministic check (e.g., ts-prune output)?

        Based on your answers I'll set up the initializer + coding agent pattern,
        with feature_list.json keyed on file batches and a PostToolUse hook that
        runs ts-prune for rules-based verification...
```

### Example session — debugging a stuck agent

```
You: My agent keeps re-reading the same files over and over and never makes
     progress. It claims it's "investigating" but produces nothing.

Claude: [skill loads — recognizes situation B]
        This is the "information access" failure mode (step 1 of the four-step
        eval). Before changing the prompt, let's check:
        - Which search tools is it using? grep/glob, or only Read?
        - Is your directory structure surfacing the right entry points, or is
          the agent pawing through files trying to figure out the layout?
        Show me the agent's tool-call transcript for one stuck run.
```

### When *not* to use the skill

This skill is opinionated about long-running, multi-step agents. It's overkill for:

- One-off scripts that happen to call the API once or twice.
- Chat UIs with no autonomous tool-calling loop.
- Quick prototypes you'll throw away in an hour.

If your "agent" is really a single LLM call wrapped in a function, ignore this skill.

---

## Bootstrapping a new harness project

```bash
# From inside your new project root
SKILL=~/.claude/skills/harness-engineering

cp $SKILL/assets/CLAUDE.md.template            ./CLAUDE.md
cp $SKILL/assets/feature_list.template.json    ./feature_list.json
cp $SKILL/assets/claude-progress.template.txt  ./claude-progress.txt
cp $SKILL/assets/init.sh.template              ./init.sh
cp $SKILL/assets/harness_skeleton.py           ./harness.py
cp $SKILL/assets/post_tool_use_lint_hook.py    ./hooks/post_tool_use_lint.py

# Then walk the audit
$EDITOR $SKILL/assets/new-harness-checklist.md
```

Substitute placeholders (project name, dev-server commands, domain context, test runner) before running anything. Run a baseline E2E *before* asking the agent to implement anything — confirm the environment is green first.

---

## Anti-pattern signals

These should interrupt the conversation immediately. Quote the matching entry from [references/anti-patterns.md](references/anti-patterns.md) back to the user.

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

> Anthropic's named **#1** failure mode is *premature victory declaration*: "a later agent instance would look around, see that progress had been made, and declare the job done." If the agent reports "complete" without test output in the transcript, treat it as not done.

---

## Source documents

All recommendations trace to Anthropic's published material:

- *Effective Harnesses for Long-Running Agents* — <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- *Building Agents with the Claude Agent SDK* — <https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk>
- *Prompting best practices — Multi-context-window workflows* — <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>
- *Claude Agent SDK overview* — <https://code.claude.com/docs/en/agent-sdk/overview.md>
- *Hooks reference* — <https://code.claude.com/docs/en/hooks.md>
- *Subagents in the SDK* — <https://code.claude.com/docs/en/agent-sdk/subagents.md>
- *Permissions* — <https://code.claude.com/docs/en/agent-sdk/permissions.md>
- *MCP integration* — <https://code.claude.com/docs/en/agent-sdk/mcp.md>

Direct quotes used in conversation live at the end of [references/principles.md](references/principles.md).

---

## Contributing

PRs welcome — especially:

- New entries in [references/anti-patterns.md](references/anti-patterns.md) with concrete recognition signals.
- Additional `assets/` templates for stacks not yet covered (TypeScript SDK harness, Go-toolchain harness, etc.).
- Updates when Anthropic publishes new harness guidance — please cite the source document and quote the relevant passage.

Keep the structure: principles in `references/`, drop-in files in `assets/`, conversational logic in `SKILL.md`.

---

## License

[MIT](LICENSE) © 2026 ShuxunoO
