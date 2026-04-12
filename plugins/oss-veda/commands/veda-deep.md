---
description: Run a thorough deep analysis of AI/ML open source opportunities with expanded sources and longer lookback
argument-hint: "[topic]"
---

Run an expanded oss-veda scan with:
- 14-day lookback instead of 7
- Top 30 repos instead of 20
- Full maintainer profile analysis
- Detailed PR merge time analysis

Topic: $ARGUMENTS (default: ai)

**You MUST execute these commands yourself with the Bash tool. Do NOT
ask the user to run them. Run all 4 steps in sequence and then
summarize the report.**

Step 0 — Guard pre-flight. Run with the Bash tool:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/guard.py --mode preflight
```

Parse the JSON. If `"hard_fail"`: show fix instructions and STOP. If
`"warnings"`: show them and continue. If `"ok"`: proceed silently.
If guard.py crashes: print "Guard unavailable" and continue.
If the user passed `--skip-guard`: skip this step.

Step 1 — execute with the Bash tool now:

```bash
TOPIC="${ARGUMENTS:-ai}"
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/run_scouts.py \
    --topic "$TOPIC" \
    --days 14 \
    --max-repos 30
```

Step 2 — after Step 1 completes, execute with the Bash tool:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/rank_opportunities.py
```

Step 3 — after Step 2 completes, execute with the Bash tool:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py
```

Then read the report output from the Bash tool result and summarize it.

Step 4 — Guard post-mortem. Run with the Bash tool:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/guard.py --mode postmortem
```

If any scouts failed, append a post-mortem diagnosis to the report.
If all succeeded, say nothing.
