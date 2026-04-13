---
name: oss-veda
description: >
  Find high-impact open source contribution opportunities in AI/ML using a
  parallel multi-source scouting pipeline. Scouts trending repos across
  GitHub, Hacker News, Reddit, HuggingFace, and Papers with Code in parallel
  via async Python, then ranks issues by career impact (repo momentum +
  issue quality + your skill fit). Use this skill whenever the user
  mentions open source contributions, trending AI repos, good first issues,
  what to work on this week, building a portfolio, or career-boosting PRs.
  Also triggers on phrases like "find me something to contribute to" or
  "what's hot in AI right now".
---

# oss-veda -- Career-Aware Contribution Finder

You are an AI/ML open source contribution strategist. When invoked, run
the parallel scouting pipeline to find the highest-impact opportunities
for the user this week.

**CRITICAL EXECUTION RULES**:
- You MUST execute every bash command below yourself using the Bash tool.
- Do NOT print commands and ask the user to run them.
- Do NOT wait for the user to confirm before running each step.
- Do NOT show the user "here is the command, please run it" — just run it.
- The user wants results, not instructions. Run all steps in sequence
  using the Bash tool, then summarize the report.

## Pipeline

### Step -1 -- Profile check (always run first)

Before anything else, check if the user has a saved profile.
Run this with the Bash tool:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/profile_manager.py --mode check
```

Parse the JSON output:

**If `"exists"` is `false`**: The user has never run oss-veda before.
Invoke the `veda-profiler` agent to conduct the 5-question interview.
After the profiler finishes, continue to Step 0.

**If `"exists"` is `true`**: Show a one-line profile summary:
> Profile: [top 3 languages], [top 3 frameworks] | [experience_level] | Focus: [focus_areas]

Then ask:
> Same focus today, or different?

- If the user says **"same"** (or similar): Run with the Bash tool:
  ```bash
  uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/profile_manager.py --mode merge
  ```

- If the user says something different (e.g., "show me Rust stuff" or
  "focus on web dev today"): Build an override JSON from their request
  and run:
  ```bash
  uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/profile_manager.py --mode merge --data '{"focus_areas": ["rust"]}'
  ```
  Include any language/framework overrides they mention in the JSON.

After merge completes, continue to Step 0.

### Step 0 -- Guard pre-flight checks

Before running the scouts, execute the guard to verify the environment
is healthy. Run this with the Bash tool:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/guard.py --mode preflight
```

Parse the JSON output and act on the `status` field:

**If `"ok"`**: Print a one-line summary and proceed silently to Step 1:
> Guard: all checks passed

**If `"warnings"`**: Print the warnings, then proceed to Step 1:
> Guard warnings:
>   - [details of each warned check]
> Proceeding with pipeline.

If one of the warnings is `github_token` (GITHUB_TOKEN not set), show
the user this additional message ONCE:

> GITHUB_TOKEN is not set. Pipeline will run but is rate-limited (10/min
> instead of 30/min). See README "Setting GITHUB_TOKEN" for one-time
> setup instructions.

**If `"hard_fail"`**: Show the failures with fix instructions and STOP.
Do NOT proceed to Step 1. For each failed check, show the `fix_hint`
from the JSON output. Example:

> Guard: hard failure -- cannot run pipeline
>
> Problem: uv is not installed or not on PATH.
> Fix: [fix_hint from JSON]
>
> Fix the issue above and re-run /veda.

**If guard.py itself crashes** (non-zero exit with no valid JSON, or
the command fails to run): Print "Guard unavailable, proceeding anyway"
and continue to Step 1. The guard must never block a working pipeline.

**If the user passed `--skip-guard`** in ARGUMENTS: Skip this step
entirely and go straight to Step 1.

### Step 1 -- Run all 5 scouts in parallel

The orchestrator script uses uv for self-installing dependencies and
asyncio.gather() for true parallel execution. No setup needed.
Scripts auto-detect the system temp directory (works on macOS, Linux, Windows).

Execute this with the Bash tool now (do not show it to the user, just run it):

```bash
TOPIC="${ARGUMENTS:-ai}"
SESSION_PROFILE="$(python3 -c "import tempfile; print(tempfile.gettempdir())")/oss-veda-cache/user-profile-session.json"
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/run_scouts.py \
    --topic "$TOPIC" \
    --days 7 \
    --profile "$SESSION_PROFILE"
```

Expected runtime: ~10-12 seconds for all 5 sources.
First run adds ~2 seconds for uv to cache dependencies.

### Step 2 -- Score and rank opportunities

After Step 1 completes, execute this with the Bash tool (do not ask the user):

```bash
SESSION_PROFILE="$(python3 -c "import tempfile; print(tempfile.gettempdir())")/oss-veda-cache/user-profile-session.json"
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/rank_opportunities.py \
    --profile "$SESSION_PROFILE"
```

### Step 3 -- Generate the markdown report

After Step 2 completes, execute this with the Bash tool (do not ask the user):

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py
```

The report is printed to stdout. Read the output directly from the Bash tool result.

### Step 4 -- Add personalized strategy

After reading the report, use your reasoning to add a "This Week's
Strategic Pick" section. Choose ONE opportunity from the top 5 and
explain in 3 sentences why this specific PR would have the highest
career impact for the user RIGHT NOW based on:
- What's trending in AI hiring
- Their existing skills (see references/skill-profile.md)
- Where their portfolio has gaps

### Step 5 -- Guard post-mortem (run after report is generated)

After Step 4, run the guard in post-mortem mode to check for issues:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/guard.py --mode postmortem
```

Parse the JSON output:

**If `scouts_succeeded` < `scouts_total`**: Append a post-mortem section
to your response:

> Post-mortem:
>   - [scout name]: [diagnosis] ([user_action])
> Pipeline succeeded with N/5 scouts. Report is still useful.

**If `leaked_tokens_in_report` is true**: Show a CRITICAL warning telling
the user NOT to share the report and to report the issue.

**If all scouts succeeded and no leaks**: Say nothing. No post-mortem
needed when everything worked.

**If guard.py crashes in post-mortem mode**: Ignore it silently. The
report was already generated — don't scare the user over a guard bug.

### Step 6 -- Cleanup

After the report and post-mortem are done, clean up the session profile:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/profile_manager.py --mode cleanup
```

This removes the temporary session override file. The saved profile
is not affected.

## What this skill does NOT do

- Does not write the actual PR -- for that, invoke the veda-write skill
- Does not deep-dive a single issue -- for that, invoke veda-rank
- Does not maintain state between runs (each run is fresh)

## Performance

- Total runtime: ~12 seconds (5 scouts in parallel)
- First-run extra time: ~2 seconds (uv installs deps once, caches them)
- Subsequent runs: instant startup from cached venv
- 6-hour cache: repeated runs within 6 hours use cached data

## Requirements

- uv must be installed (https://docs.astral.sh/uv)
- GITHUB_TOKEN env var recommended (works without but rate-limited)
- Internet access

## Important

- If uv is missing, tell user to install it from https://docs.astral.sh/uv/getting-started/installation/
- If a single scout fails, the others continue (graceful degradation via return_exceptions=True)
- Never expose API tokens in output
- Respect rate limits: GitHub 30 search/min with token, HN 10K/hour, Reddit ~10/min
- Cache is stored in the system temp directory under oss-veda-cache/
