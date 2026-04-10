# Career-Impact Scoring Algorithm (v1.1.0)

## Formula

```
Career Impact Score = (0.40 × Repo Score) + (0.35 × Issue Score) + (0.25 × Fit Score)
```

All scores are normalized to 0-100. Weights are configurable in `config.json`.

## Repo Score (max 100 points)

| Signal | Weight | Calculation |
|---|---|---|
| Star momentum | 25% | Logarithmic scale: `log10(stars) / 6 × 100` — small fast-growing repos compete with giants |
| Social buzz | 20% | Combined HN points + Reddit score + HuggingFace likes, log-normalized |
| Community health | 20% | Fork-to-star ratio: 5-40% = healthy (80), >40% = declining (60), <5% = early (40) |
| Push recency | 20% | Last push: <1 day = 100, <7 days = 85, <30 days = 60, older = 30 |
| PR merge rate | 15% | Placeholder (65) — requires additional API calls for full implementation |

## Issue Score (max 100 points)

| Signal | Weight | Calculation |
|---|---|---|
| Label quality | 25% | Stacking bonuses: good-first-issue (+40), help-wanted (+30), bug (+25), enhancement (+20), hacktoberfest (+10). Base 30, capped at 100 |
| Freshness | 25% | Exponential decay: `100 × e^(-0.693 × days / half_life)`. Configurable half-life (default: 30 days) |
| Engagement | 20% | Sweet spot: 0 comments = 30, 1-3 = 100 (ideal), 4-8 = 80, 9-15 = 50, 16+ = 20 |
| Competition | 15% | Unassigned + 0 comments = 95 (wide open), else 80 |
| Complexity | 15% | Structural signals (steps to reproduce, checkboxes, acceptance criteria) + body length |

**Filtering:** Assigned issues return -1 and are excluded entirely.

## Fit Score (max 100 points)

| Signal | Weight | Calculation |
|---|---|---|
| Language match | 30% | Proficiency from skill profile (e.g. Python=100, TypeScript=70). Unknown language = 15 (soft scoring, no hard-filter) |
| Framework match | 40% | Fuzzy match repo topics/description against known frameworks from config |
| Skill level | 30% | Default 70 (configurable per user experience level) |

## Implementation

The `rank_opportunities.py` script implements this formula. Each repo/issue
pair gets a composite score. Results are sorted descending. Top 20 are
"recommended", next 5 are "long-shot high-reward". All configurable via `config.json`.
