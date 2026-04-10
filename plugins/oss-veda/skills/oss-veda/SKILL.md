---
name: oss-veda
description: >
  Find high-impact open source contribution opportunities in AI/ML using a
  parallel multi-source scouting pipeline. Scouts trending repos across
  GitHub, Hacker News, Reddit, HuggingFace, and Papers with Code in parallel
  via async Python, then ranks issues by career impact (repo momentum +
  maintainer visibility + your skill fit). Use this skill whenever the user
  mentions open source contributions, trending AI repos, good first issues,
  what to work on this week, building a portfolio, or career-boosting PRs.
  Also triggers on phrases like "find me something to contribute to" or
  "what's hot in AI right now".
---

# oss-veda — Career-Aware Contribution Finder

You are an AI/ML open source contribution strategist. When invoked, run
the parallel scouting pipeline to find the highest-impact opportunities
for the user this week.

## Pipeline

### Step 1 — Run all 5 scouts in parallel

The orchestrator script uses uv for self-installing dependencies and
asyncio.gather() for true parallel execution. No setup needed.

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/run_scouts.py \
    --topic "$ARGUMENTS" \
    --days 7 \
    --output /tmp/oss-veda-raw.json
```

Expected runtime: ~10-12 seconds for all 5 sources.
First run adds ~2 seconds for uv to cache dependencies.

### Step 2 — Score and rank opportunities

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/rank_opportunities.py \
    --input /tmp/oss-veda-raw.json \
    --output /tmp/oss-veda-ranked.json
```

### Step 3 — Generate the markdown report

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py \
    --input /tmp/oss-veda-ranked.json \
    --output /tmp/oss-veda-report.md
cat /tmp/oss-veda-report.md
```

### Step 4 — Add personalized strategy

After reading the report, use your reasoning to add a "This Week's
Strategic Pick" section. Choose ONE opportunity from the top 5 and
explain in 3 sentences why this specific PR would have the highest
career impact for the user RIGHT NOW based on:
- What's trending in AI hiring
- Their existing skills (see references/skill-profile.md)
- Where their portfolio has gaps

## What this skill does NOT do

- Does not write the actual PR — for that, invoke the veda-write skill
- Does not deep-dive a single issue — for that, invoke veda-rank
- Does not maintain state between runs (each run is fresh)

## Performance

- Total runtime: ~12 seconds (5 scouts in parallel)
- First-run extra time: ~2 seconds (uv installs deps once, caches them)
- Subsequent runs: instant startup from cached venv
- Idle token cost: ~120 tokens (just metadata)
- Active token cost: ~3,500 tokens (this file + pipeline output)

## Requirements

- uv must be installed (https://docs.astral.sh/uv)
- GITHUB_TOKEN env var (or gh auth login configured)
- Internet access

## Important

- If uv is missing, scripts fail with clear error. Tell user to run: curl -LsSf https://astral.sh/uv/install.sh | sh
- If a single scout fails, the others continue (graceful degradation via return_exceptions=True)
- Never expose API tokens in output
- Respect rate limits: GitHub 30 search/min, HN 10K/hour, Reddit ~10/min for public JSON
- Cache results in /tmp/oss-veda-cache/ with 6-hour TTL
