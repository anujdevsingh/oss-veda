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

Use the oss-veda skill with extended parameters:

```bash
TOPIC="${ARGUMENTS:-ai}"
${CLAUDE_PLUGIN_ROOT}/scripts/run_scouts.py \
    --topic "$TOPIC" \
    --days 14 \
    --max-repos 30
```

Then proceed with ranking and report generation as normal.
