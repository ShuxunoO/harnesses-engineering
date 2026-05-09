# Evaluation: The Four-Step Method

This file expands the evaluation cadence Anthropic recommends. Evaluation is not a one-time pre-launch step — it belongs inside the development loop.

---

## The four steps

| # | Step | Question | Fix when it fails |
|---|---|---|---|
| 1 | **Information access** | Can the agent reach the information it needs? | Restructure / rename / add a domain search tool |
| 2 | **Systematic failures** | Does the same kind of error recur? | Encode the rule into a `PreToolUse` hook |
| 3 | **Self-correction** | When it errs, can it recover? | Add creative tools (Bash, code generation) |
| 4 | **Regression** | Did adding new behavior break old cases? | Run a programmatic eval against a real-prompt test set |

---

## 1. Information access

**The question.** With the current tool set and file system, can the agent *find* and *read* what it needs to complete the task?

### Diagnose

While running a test set, watch for:

- Repeated `grep` with the wrong keywords (names aren't semantic enough).
- Searching in directories where the answer can't live (structure isn't clear).
- "I can't find X" (the codebase doesn't have X, or the agent doesn't know what X is called).

### Fix, in order of cost

1. **Rename / restructure files and directories.** Zero-code, often the highest-impact change. Splitting `utils.py` into `auth_utils.py` / `email_utils.py` makes a single `grep` succeed.
2. **Add documentation next to the code.** A `README.md` in the relevant module is picked up automatically when the agent greps.
3. **Add a domain-specific search tool** — only when the first two are not enough. Don't add a "generic search"; add a domain verb.
4. **Last resort: a retrieval layer.** See Principle 1.

### Anti-examples

- "It got the wrong answer, so we need more context" → jump to vector DB. The real cause might be a bad file name.
- A new tool is added but the agent doesn't know when to call it — the tool description is too vague.

---

## 2. Systematic failures

**The question.** Are the failures *repeated*? Same class of error N times?

This is the highest-value diagnostic. Repeats mean the issue is in harness design, not "the model didn't think of it this time."

### Diagnose

Run the regression set and look at error patterns:

- Always wrong about a specific API parameter.
- Always panics on a category of input.
- Always forgets a required prerequisite step.

### Fix — convert the pattern into a hook

This is the core idea. Examples:

| Pattern | Hook fix |
|---|---|
| Always forgets to authenticate before calling an API | `PreToolUse(callApi)` checks session validity; blocks with a hint when invalid |
| Always passes ms when seconds are required | `PreToolUse(...)` validates parameter range; rejects with a unit hint |
| Always forgets to lint before commit | `PreToolUse(Bash)` intercepts `git commit`, runs lint, blocks on failure |
| Always edits `feature_list.json` `steps` | `PreToolUse(Write|Edit)` on that file checks the diff; only `passes` / `last_verified_commit` allowed |

**Hook, not prompt.** Rewriting the system prompt is a bet that "this time the model will remember." A hook is deterministic. If the same pattern has repeated three times, the prompt has already lost.

### Anti-examples

- The agent keeps making the same mistake; you write the fifth version of the system prompt with "IMPORTANT: don't forget to..." — it will forget again.
- Telling the user to remind the agent every time. That offloads a harness bug to the user.

---

## 3. Self-correction

**The question.** After the first error, can the agent diagnose and recover?

A healthy harness assumes the agent will err sometimes. What matters is whether it can climb out.

### Diagnose

Trigger a known-bad prompt (or replay a real failure) and watch:

- What does it do after seeing the error?
- Does it try a different approach?
- Is it stuck on a single tool that can't solve the problem?

### Fix — give it creative tools

The principle: don't pin the agent to one rigid API. Examples:

| Stuck pattern | Fix |
|---|---|
| `searchUsers(filters)` is the only option, but filters can't express the query | Add Bash + DB CLI; let it write SQL |
| Vector search misses semantically; agent has no fallback | Add `Grep` / `Glob` |
| `editFile` is the only tool; agent can't refactor at scale | Allow code generation; let it write a codemod |
| Test runner is monolithic; agent can't probe a single step | Add Bash for `echo` / step-by-step probing |

**General rule.** Bash is the most under-rated self-correction tool. With a shell the agent can write probes, grep its own state, change env vars, read logs — the *creative* moves that pull it out of a corner.

### Anti-examples

- Hand the agent more narrow APIs and it ping-pongs between them — it needs flexibility, not more specificity.
- Add a prompt instruction "if X fails, try Y" — give it the tool, and it will find Y on its own.

---

## 4. Regression

**The question.** After adding a feature, changing a prompt, or wiring a new tool, do the old cases still pass?

Without regression testing, every change is a gamble.

### Required infrastructure

1. **A test set drawn from real usage.** Sources: production logs, user feedback, support tickets, bug reports. Start at 30–100 prompts and grow.
2. **A programmatic eval runner.** A script that runs the full set and produces statistics.
3. **An expected outcome per case.** One of:
   - Assertion list (output contains X, tool Y was called, file Z exists).
   - Reference output (diff against it).
   - Rubric (which dimensions to score).
4. **Fast.** A full regression in under 30 minutes. If it takes longer, that's a bug — parallelize.

### Cadence

- Before merging to main.
- Around every change to prompts, tools, or hooks.
- Before significant releases.

### Test-set shape

```json
{
  "evals": [
    {
      "id": 1,
      "prompt": "Plot last week's sales as a line chart.",
      "context_files": ["data/sales_2026_w18.csv"],
      "assertions": [
        {"name": "Read tool used on CSV", "type": "tool_used", "tool": "Read"},
        {"name": "Final output is a .png file", "type": "file_exists", "pattern": "*.png"},
        {"name": "Tool calls < 20", "type": "tool_count", "max": 20}
      ]
    }
  ]
}
```

### Anti-examples

- A test set written by developers from intuition. It doesn't reflect real usage; passing it does not mean users are unaffected.
- Regression takes two hours. Developers stop running it. Changes ship blind.
- Different runs produce different scores; people say "the agent's mood today." Without temperature 0 (or sampling means), results aren't comparable.

---

## How evaluation feeds development

```
+------------------+
| Edit harness     |
+--------+---------+
         |
         v
+------------------+
| Run regression   |   <-- step 4
+--------+---------+
         | (failures)
         v
+------------------+
| Pattern in       |   <-- step 2
| failures?        |
+--------+---------+
         |
   +-----+------+
   |            |
   yes          no
   |            |
   v            v
+--------+   +----------------+
| Hook   |   | Info access?   |   <-- step 1
+--------+   +-------+--------+
                     |
               +-----+------+
               |            |
               yes          no
               |            |
               v            v
       +---------------+   +----------------+
       | Restructure / |   | Creative tools |   <-- step 3
       | docs          |   +----------------+
       +---------------+
```

**Operating intuition.** Each eval failure is not "the model is dumb"; it is "the harness didn't make this case easy enough." The harness engineer's question: *what change to the harness would make this case stop failing?*

---

## Evaluation anti-patterns

- **Vibe-eval.** Run 5 cases, feel good, ship.
- **Over-reliance on LLM-as-judge** for regression — slow, expensive, unstable.
- **Test set is just prompts** with no expected outcome — the run says nothing.
- **Editing harness without re-running regression** — every change is a gamble; quality decays.
- **Slow regression** — the cost of running it pushes people to skip it. Then you have nothing.

---

## A minimal eval runner sketch

```python
# eval_runner.py
import asyncio, json
from claude_agent_sdk import query, ClaudeAgentOptions

async def run_one(eval_case, options):
    transcript = []
    async for msg in query(prompt=eval_case["prompt"], options=options):
        transcript.append(msg)
    return transcript

def grade(transcript, assertions):
    results = []
    for a in assertions:
        if a["type"] == "tool_used":
            passed = any(getattr(m, "name", None) == a["tool"] for m in transcript)
        elif a["type"] == "file_exists":
            import glob
            passed = bool(glob.glob(a["pattern"]))
        # ... other assertion types
        results.append({"name": a["name"], "passed": passed})
    return results

async def main():
    evals = json.load(open("evals.json"))
    options = ClaudeAgentOptions(...)
    summary = []
    for e in evals["evals"]:
        t = await run_one(e, options)
        results = grade(t, e["assertions"])
        summary.append({"id": e["id"], "results": results})
    print(json.dumps(summary, indent=2))

asyncio.run(main())
```

In production, prefer pytest + custom fixtures — a familiar tool chain rather than a homegrown runner.
