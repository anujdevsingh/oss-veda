---
name: veda-rank
description: >
  Deep-dive analysis of a specific GitHub issue to assess whether it's worth
  contributing to. Use this skill when the user pastes a GitHub issue URL or
  asks "should I work on this issue?" or "is this a good issue for me?" or
  "analyze this issue". Fetches the issue details, repo health, maintainer
  profile, and recent PRs, then scores it using the career-impact formula.
  Returns a clear verdict: high impact (do it), medium (worth considering),
  or low ROI (skip).
---

# veda-rank — Issue Deep-Dive Analyzer

When the user provides a GitHub issue URL, analyze it for career impact.

## Pipeline

1. Parse the issue URL to extract owner, repo, and issue number
2. Fetch the issue details via GitHub API:
   ```bash
   curl -sH "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/{owner}/{repo}/issues/{number}"
   ```
3. Fetch repo health metrics:
   ```bash
   curl -sH "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/{owner}/{repo}"
   ```
4. Fetch recent PRs to calculate merge rate:
   ```bash
   curl -sH "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/{owner}/{repo}/pulls?state=closed&per_page=30"
   ```
5. Check issue comments for maintainer engagement
6. Score using the formula in references/scoring.md
7. Check skill fit against references/skill-profile.md

## Output format

```
## Issue Analysis: {issue_title}

**Repo:** {owner}/{repo} (⭐ {stars})
**Issue:** #{number} — {title}
**Labels:** {labels}
**Age:** {days} days
**Comments:** {count} ({maintainer_engaged: yes/no})

### Career Impact Score: {score}/100

| Signal | Score | Detail |
|---|---|---|
| Repo momentum | {x}/100 | {explanation} |
| Issue quality | {x}/100 | {explanation} |
| Your skill fit | {x}/100 | {explanation} |

### Verdict: {HIGH IMPACT / MEDIUM / LOW ROI}

{2-3 sentence strategic reasoning}

### Suggested approach (if verdict is HIGH or MEDIUM)

{Specific PR strategy in 3-4 sentences}
```
