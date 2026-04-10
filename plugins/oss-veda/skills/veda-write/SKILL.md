---
name: veda-write
description: >
  Draft a contribution for a specific GitHub issue. Use this skill when the
  user says "write a PR for this", "draft a contribution", "help me
  contribute to this issue", or has already analyzed an issue with veda-rank
  and wants to proceed. Fetches the repo's CONTRIBUTING.md, recent merged
  PRs for style reference, and the relevant code, then drafts the PR title,
  body, and an initial comment to post on the issue announcing intent.
---

# veda-write — Contribution Drafter

When the user wants to contribute to a specific issue, draft the full PR.

## Pipeline

1. Fetch the issue details and repo info
2. Fetch the repo's CONTRIBUTING.md (if it exists):
   ```bash
   curl -sH "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/{owner}/{repo}/contents/CONTRIBUTING.md"
   ```
3. Fetch 5 recently merged PRs to learn the style:
   ```bash
   curl -sH "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=5"
   ```
4. Read the issue body and comments thoroughly
5. Draft the following:

## Output format

### 1. Issue comment (to announce intent)

```markdown
Hi! I'd like to work on this issue. Here's my planned approach:

{2-3 sentences describing what you'll do}

I expect to have a PR ready within {timeframe}. Let me know if this
approach sounds good or if you'd suggest a different direction!
```

### 2. PR title

Follow the repo's convention (look at recent merged PRs). Usually:
`{type}: {short description}` or `{short description} (#{issue_number})`

### 3. PR body

```markdown
## Summary
{What this PR does in 2-3 sentences}

## Changes
{Bullet list of specific changes}

## Related issue
Closes #{issue_number}

## Testing
{How to verify the changes work}
```

### 4. Suggested code changes

If the issue is clear enough, draft the actual code changes. Otherwise,
outline the approach with pseudocode and file paths.

## Important

- Always check CONTRIBUTING.md first for submission guidelines
- Match the repo's code style (look at existing files)
- Keep the PR focused — one issue, one PR
- Never auto-submit — always show the draft to the user first
