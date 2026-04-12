# oss-veda

**Wisdom for your next open source contribution.**

A Claude Code plugin that scouts trending AI/ML repositories across 5 data sources in parallel, then ranks contribution opportunities by career impact -- combining repo momentum, issue quality, and your personal skill fit. A guard agent verifies your environment and secures the pipeline end-to-end.

---

## Table of Contents

- [Install](#install)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Scoring Algorithm](#scoring-algorithm)
- [Configuration](#configuration)
- [Data Sources](#data-sources)
- [Skills & Commands](#skills--commands)
- [Requirements](#requirements)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Install

```bash
# Add the marketplace
/plugin marketplace add anujdevsingh/anuj-ai-tools

# Install oss-veda
/plugin install oss-veda@anuj-ai-tools
```

## Usage

### Quick scan (7-day lookback)
```bash
/veda
```

### Deep scan (14-day lookback, more repos)
```bash
/veda-deep
```

### Natural language
Just ask Claude any of these:
- *"What should I contribute to this week?"*
- *"Find me something to contribute to"*
- *"What's hot in AI right now?"*
- *"Show me good first issues in LLM repos"*

### Analyze a specific issue
Paste a GitHub issue URL and ask: *"Should I work on this?"*
This triggers the `veda-rank` skill for deep-dive analysis.

### Draft a contribution
After finding an issue, say: *"Help me contribute to this"*
This triggers the `veda-write` skill to draft the PR.

---

## How It Works

```
                         /veda
                           |
                       guard.py
                     (pre-flight)
                           |
                    run_scouts.py
                    (orchestrator)
                           |
            +--------------+--------------+
            |       |       |      |      |
         GitHub    HN    Reddit   HF    PwC
         scout   scout   scout  scout  scout
            |       |       |      |      |
            +--------------+--------------+
                           |
                  oss-veda-raw.json
                           |
                 rank_opportunities.py
                   (scoring engine)
                           |
                 oss-veda-ranked.json
                           |
                  generate_report.py
                           |
                 Markdown report + strategic pick
                           |
                       guard.py
                    (post-mortem)
```

### Pipeline steps

0. **Guard pre-flight** -- Verifies environment health: uv installed, Python >= 3.11, network reachable, GITHUB_TOKEN set, script checksums intact, config valid. Hard failures block the pipeline; soft warnings continue.

1. **Scout** (parallel) -- 5 async scouts fetch trending repos, posts, models, and papers from GitHub, Hacker News, Reddit, HuggingFace, and Papers with Code simultaneously using `asyncio.gather()`.

2. **Rank** -- Each repo+issue pair is scored on 3 axes (repo momentum, issue quality, skill fit) producing a composite career impact score out of 100.

3. **Report** -- Top 20 opportunities are formatted into a markdown report with executive summary, ranked table, and long-shot picks.

4. **Strategy** -- Claude adds a personalized "This Week's Strategic Pick" based on your skill profile and current AI hiring trends.

5. **Guard post-mortem** -- Checks scout success rates, verifies report was generated, scans output for leaked tokens. Appends diagnosis if any scouts failed.

---

## Guard Agent

Every `/veda` and `/veda-deep` run starts with an automatic guard check (~3 seconds). The guard verifies your environment is healthy and safe before running the pipeline.

### What the guard checks

| Category | Checks | Severity |
|----------|--------|----------|
| **Pre-flight** | uv installed, Python >= 3.11, temp dir writable, network reachable, GITHUB_TOKEN set, scripts exist, config.json valid | Hard/Soft |
| **Security** | Cache dir < 100 MB, no unexpected files, script SHA256 checksums match, history file integrity | Hard/Soft |
| **Post-mortem** | Scout success rate, report file generated, no leaked tokens in output | Hard/Soft |

### Severity levels

- **Hard fail**: Pipeline cannot run. Guard blocks and shows fix instructions.
- **Soft warning**: Pipeline can still produce useful results. Guard warns and continues.
- **Pass**: Silent. No extra output.

### Skipping the guard

If the guard blocks you incorrectly (e.g. corporate proxy blocks the network check):

```bash
/veda --skip-guard
/veda-deep --skip-guard
```

### Guard self-protection

If the guard itself crashes, the pipeline runs anyway. The guard never blocks a working pipeline due to its own bugs.

---

## Architecture

```
oss-veda/
|-- .claude-plugin/
|   |-- plugin.json                    # Plugin manifest
|-- skills/
|   |-- oss-veda/
|   |   |-- SKILL.md                   # Main skill: find opportunities
|   |   |-- references/
|   |       |-- api-endpoints.md       # API endpoint reference
|   |       |-- scoring.md             # Scoring algorithm docs
|   |       |-- skill-profile.md       # Default user profile
|   |-- veda-rank/
|   |   |-- SKILL.md                   # Deep-dive issue analyzer
|   |-- veda-write/
|       |-- SKILL.md                   # Contribution drafter
|-- agents/
|   |-- github-scout.md               # GitHub trending repos + issues
|   |-- hn-scout.md                    # Hacker News Show HN posts
|   |-- reddit-scout.md               # Reddit AI subreddits
|   |-- hf-scout.md                   # HuggingFace trending models/spaces
|   |-- pwc-scout.md                  # Papers with Code linked repos
|   |-- veda-guard.md                 # Guard agent (pre-flight + post-mortem)
|-- commands/
|   |-- veda.md                        # /veda slash command
|   |-- veda-deep.md                   # /veda-deep slash command
|-- scripts/
|   |-- run_scouts.py                  # Orchestrator (parallel execution)
|   |-- github_scout.py               # GitHub Search API client
|   |-- hn_scout.py                    # HN Algolia API client
|   |-- reddit_scout.py               # Reddit public JSON client
|   |-- hf_scout.py                    # HuggingFace API client
|   |-- pwc_scout.py                   # Papers with Code API client
|   |-- rank_opportunities.py          # Career impact scoring engine
|   |-- generate_report.py             # Markdown report generator
|   |-- guard.py                       # Environment & security guard
|   |-- _dev_update_checksums.py       # Dev-only: regenerate checksums.json
|-- config.json                        # Centralized configuration
|-- checksums.json                     # SHA256 hashes for script integrity
|-- README.md
```

### Key design decisions

- **uv single-file scripts** -- Each Python script uses PEP 723 inline metadata (`# /// script`). Dependencies are declared per-file and auto-installed by `uv` on first run. No global `requirements.txt`, no shared virtual environment.

- **Native Claude subagents** -- 6 agents (5 scouts + 1 guard) are markdown files in `agents/`. Scout agents can be invoked independently by Claude for targeted searches beyond the standard pipeline.

- **Guard agent with checksum verification** -- `guard.py` runs 14 checks across pre-flight, security, and post-mortem phases. Script integrity is verified via SHA256 checksums (with CRLF normalization for cross-platform consistency). Tiered severity (hard fail / soft warning / pass) ensures the pipeline only blocks on real problems.

- **Graceful degradation** -- If any scout fails (rate limit, network error, API down), the others continue. `asyncio.gather(return_exceptions=True)` ensures one failure never kills the pipeline.

- **Per-scout timeouts** -- Each scout has a 3-minute timeout via `asyncio.wait_for()`. A hung scout is killed and reported, not silently blocking.

- **Exponential backoff** -- GitHub API calls retry with exponential backoff on 403/429 responses (5s, 10s, give up). Respects `Retry-After` headers.

- **6-hour cache** -- Results are cached per topic+days in the system temp directory. Repeated runs within 6 hours use cached data. Cache corruption is auto-detected and recovered.

- **Run history** -- Every pipeline run is logged to `run_history.tsv` in the cache directory, tracking scout success rates, result counts, and timing over time.

---

## Scoring Algorithm

```
Career Impact Score = (0.40 x Repo Score) + (0.35 x Issue Score) + (0.25 x Fit Score)
```

All scores normalized to 0-100. Weights are configurable in `config.json`.

### Repo Score (0-100)

| Signal | Weight | Method |
|--------|--------|--------|
| Star momentum | 25% | Logarithmic scale: `log10(stars) / 6 * 100` -- small fast-growing repos compete with giants |
| Social buzz | 20% | Combined HN points + Reddit score + HuggingFace likes, log-normalized |
| Community health | 20% | Fork-to-star ratio: 5-40% = healthy (80), >40% = declining (60), <5% = early (40) |
| Push recency | 20% | Last push: <1 day = 100, <7 days = 85, <30 days = 60, older = 30 |
| PR merge rate | 15% | Placeholder (65) -- requires additional API calls for full implementation |

### Issue Score (0-100)

| Signal | Weight | Method |
|--------|--------|--------|
| Label quality | 25% | Stacking bonuses: good-first-issue (+40), help-wanted (+30), bug (+25), enhancement (+20), hacktoberfest (+10). Capped at 100 |
| Freshness | 25% | Exponential decay: `100 * e^(-0.693 * days / half_life)`. Configurable half-life (default: 30 days) |
| Engagement | 20% | Sweet spot: 1-3 comments = 100 (maintainer engaged), 4-8 = 80, 9-15 = 50, 16+ = 20 (likely stuck) |
| Competition | 15% | Unassigned + 0 comments = 95 (wide open), else 80 |
| Complexity | 15% | Checks body for structural signals (steps to reproduce, checkboxes, acceptance criteria) + length |

### Fit Score (0-100)

| Signal | Weight | Method |
|--------|--------|--------|
| Language match | 30% | Proficiency from skill profile (Python=100, TypeScript=70, unknown=15) |
| Framework match | 40% | Fuzzy match repo topics/description against known frameworks |
| Skill level | 30% | Default 70 (configurable per user experience level) |

**Filtering:**
- Assigned issues are excluded (someone is already working on it)
- No language hard-filters -- unfamiliar languages get low fit score (15) but are still ranked

---

## Configuration

All settings live in `config.json` at the plugin root:

```json
{
  "skill_profile": {
    "languages": { "python": 1.0, "typescript": 0.7 },
    "frameworks": { "pytorch": 0.9, "langchain": 0.8 }
  },
  "scouts": {
    "github_ai_topics": ["llm", "langchain", "rag", "agents", ...],
    "reddit_subreddits": ["MachineLearning", "LocalLLaMA", "LangChain"],
    "hf_endpoints": ["models", "spaces"],
    "hn_queries": ["AI OR LLM", "open source AI", ...],
    "pwc_queries": ["large language model", "AI agents", ...]
  },
  "scoring": {
    "freshness_half_life_days": 30,
    "repo_weight": 0.40,
    "issue_weight": 0.35,
    "fit_weight": 0.25,
    "top_n": 20,
    "long_shot_n": 5
  },
  "cache_ttl_seconds": 21600,
  "scout_timeout_seconds": 180
}
```

### Customizing for your profile

Edit the `skill_profile` section to match your skills. Proficiency values are 0.0 to 1.0:

- **1.0** = primary language/framework, use daily
- **0.7-0.9** = comfortable, used in projects
- **0.5-0.6** = familiar, can contribute with some ramp-up
- **0.0-0.4** = learning or unfamiliar

---

## Data Sources

| Source | API | Auth | Rate Limit | What it finds |
|--------|-----|------|------------|---------------|
| **GitHub** | REST v3 Search | `GITHUB_TOKEN` (recommended) | 30 search/min with token, 10/min without | Trending repos by topic, good-first-issues, help-wanted issues |
| **Hacker News** | Algolia | None | 10,000/hr | Show HN posts with GitHub links, high-engagement AI/ML projects |
| **Reddit** | Public JSON | User-Agent header | ~10/min | Top posts from r/MachineLearning, r/LocalLLaMA, r/LangChain with GitHub links |
| **HuggingFace** | REST | None | Generous | Trending models and Spaces by trending score |
| **Papers with Code** | REST v1 | None | Generous | Papers with linked GitHub implementations |

---

## Skills & Commands

### Skills

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `oss-veda` | "What should I contribute to?" / "Find trending AI repos" | Runs full 5-scout pipeline, ranks by career impact, generates report |
| `veda-rank` | Paste a GitHub issue URL + "Should I work on this?" | Deep-dives a single issue: repo health, maintainer engagement, skill fit |
| `veda-write` | "Help me contribute to this issue" | Drafts: issue comment (announcing intent), PR title, PR body, suggested code changes |

### Commands

| Command | Description |
|---------|-------------|
| `/veda [topic] [--skip-guard]` | Quick scan: 7-day lookback, top 20 repos |
| `/veda-deep [topic] [--skip-guard]` | Deep scan: 14-day lookback, top 30 repos, full maintainer analysis |

---

## Requirements

| Requirement | Why | Install |
|-------------|-----|---------|
| **uv** | Runs Python scripts with auto-installed dependencies | See [uv docs](https://docs.astral.sh/uv/getting-started/installation/) |
| **Python 3.11+** | Required by all scout scripts | [python.org](https://python.org) |
| **GITHUB_TOKEN** | GitHub Search API needs auth for adequate rate limits | [Create token](https://github.com/settings/tokens) with `public_repo` scope |
| **Internet** | Fetches from 5 external APIs | -- |

### Setting GITHUB_TOKEN (one-time setup)

The plugin works without a token but is rate-limited to **10 searches/minute**. Adding a token raises this to **30 searches/minute** and gives you cleaner runs without backoff delays.

#### Step 1 — Create a GitHub Personal Access Token

1. Go to **https://github.com/settings/tokens** (or: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic))
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. **Note**: `oss-veda plugin`
4. **Expiration**: 90 days (or longer if you prefer)
5. **Scopes**: Leave **all checkboxes unchecked**. The plugin only reads public data — it does not need any scopes. An unscoped token still gets the higher rate limit.
6. Click **"Generate token"** at the bottom
7. **Copy the token immediately** (starts with `ghp_...`) — GitHub only shows it once

#### Step 2 — Save it to your shell environment

**macOS / Linux (zsh):**
```bash
echo 'export GITHUB_TOKEN="ghp_your_token_here"' >> ~/.zshrc
source ~/.zshrc
```

**macOS / Linux (bash):**
```bash
echo 'export GITHUB_TOKEN="ghp_your_token_here"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell — permanent, user-level):**
```powershell
[Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "ghp_your_token_here", "User")
```
Then **close and reopen your terminal** so the new variable is picked up.

**Windows (GUI alternative):**
Settings → System → About → Advanced system settings → Environment Variables → New
- Name: `GITHUB_TOKEN`
- Value: your token

#### Step 3 — Verify

Open a new terminal and run:

```bash
# macOS/Linux
echo $GITHUB_TOKEN

# Windows PowerShell
echo $env:GITHUB_TOKEN
```

You should see your token printed. Now run `/veda` in Claude Code — the rate-limit warning should be gone.

#### Security notes

- **Never paste your token into Claude Code chat.** The plugin reads it from your shell environment automatically — it never needs to appear in the conversation.
- **No scopes needed.** An unscoped classic token can only read public data, so even if it leaks it cannot do anything destructive.
- **The plugin never logs, prints, or transmits your token** — it only sends it as the `Authorization` header to `api.github.com`.

---

## Troubleshooting

### "Rate limit exceeded" errors on GitHub scout

GitHub Search API allows 30 requests/minute. If you run the pipeline twice within a minute, the second run will hit rate limits. The backoff system handles this automatically -- wait 1-2 minutes and retry.

### "GITHUB_TOKEN not set" warning

The GitHub scout works without a token but is limited to 10 searches/minute (vs 30 with token). Set the token as described above.

### Papers with Code returns 0 results

The PwC API is occasionally unavailable. This is handled gracefully -- the other 4 scouts continue. Results will be slightly less comprehensive but still useful.

### Unicode/encoding errors on Windows

Fixed in v1.1.0. All file writes use `encoding="utf-8"` and stdout is reconfigured for Unicode support.

### Cache issues

If results seem stale, bypass the cache:
```bash
# Via command
/veda --no-cache

# Via script directly
uv run scripts/run_scouts.py --no-cache
```

Cache files are stored in your system temp directory under `oss-veda-cache/`.

---

## Run History

Every pipeline execution is logged to `{tempdir}/oss-veda-cache/run_history.tsv`:

```
timestamp            topic  days  scouts_ok  elapsed_s  repos  issues  hn  reddit  hf  pwc
2026-04-10T10:50:43  ai     7     5/5        122.4      20     29      29  1       40  0
```

Use this to track scout reliability and result trends over time.

---

## Version History

### v1.2.0 (Current)

- **Guard agent** -- New `guard.py` with 14 environment, security, and post-mortem checks. Runs automatically at pipeline start (pre-flight) and end (post-mortem). Tiered severity: hard fail blocks, soft warning continues, pass is silent.
- **Script integrity verification** -- SHA256 checksums for all scripts (`checksums.json`). Guard detects tampered or corrupted scripts before execution. CRLF-normalized hashing for cross-platform consistency.
- **`--skip-guard` escape hatch** -- Bypass guard checks for edge cases (e.g. corporate proxies blocking network check).
- **Dev helper** -- `_dev_update_checksums.py` regenerates checksums after editing scripts.
- **Guard self-protection** -- If guard.py itself crashes, the pipeline runs anyway.

### v1.1.1

- Fixed HuggingFace URLs (now correctly links to `huggingface.co/{id}`)
- Added JSON decode error handling in HuggingFace and Reddit scouts
- Fixed `Retry-After` header parsing to handle HTTP-date format
- Added path traversal protection on cache file paths
- Added defensive `.get()` access throughout report generator
- Guarded against missing `objectID` in Hacker News results
- Removed unused `httpx`/`pydantic` dependencies from scoring script
- Fixed missing `encoding="utf-8"` on cache file reads
- Updated scoring reference docs to match v1.1.0 algorithm
- Fixed `/veda-deep` command to default topic to "ai" when no argument given

### v1.1.0

- Logarithmic star scoring (small fast-growing repos now compete with giants)
- Exponential freshness decay with configurable half-life
- Engagement sweet-spot detection (1-3 comments = ideal)
- Structural complexity analysis (checks for steps, checkboxes, acceptance criteria)
- Soft language scoring (no more hard-filtering Go/Rust/Java repos)
- HuggingFace likes/downloads included in social signals
- Centralized `config.json` for all settings
- Exponential backoff with retry on GitHub 403/429
- Per-scout 3-minute timeout via `asyncio.wait_for()`
- Run history tracking (TSV log)
- Windows compatibility (no hardcoded `/tmp` paths)
- Fixed `datetime.utcnow()` deprecation warnings
- Report shows next scan date as tomorrow

### v1.0.0

- Initial release
- 5 parallel scouts (GitHub, HN, Reddit, HuggingFace, Papers with Code)
- Career impact scoring
- 3 skills, 5 scout agents, 2 commands

---

## License

MIT -- see [LICENSE](LICENSE)
