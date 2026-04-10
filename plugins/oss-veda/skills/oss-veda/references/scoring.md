# Career-Impact Scoring Algorithm

## Formula

```
Career Impact Score = (0.4 × Repo Score) + (0.35 × Issue Score) + (0.25 × Fit Score)
```

All scores are normalized to 0-100.

## Repo Score (max 100 points)

| Signal | Weight | Calculation |
|---|---|---|
| Star velocity | 30% | stars_last_7d / max_stars_last_7d × 100 |
| Social buzz | 20% | (hn_points + reddit_score + hf_likes) / max_social × 100 |
| Maintainer visibility | 20% | GitHub followers of top 3 maintainers, normalized |
| PR merge rate | 15% | merged_prs / (merged_prs + closed_prs) × 100 |
| Issue response time | 15% | inverse_normalize(median_first_response_hours) |

## Issue Score (max 100 points)

| Signal | Weight | Calculation |
|---|---|---|
| Label quality | 25% | good-first-issue=80, help-wanted=60, bug=70, docs=40, feature=50 |
| Freshness | 25% | max(0, 100 - days_since_creation × 2) |
| Maintainer engagement | 20% | Maintainer commented? +50. Has assignee? -30. |
| Competition | 15% | max(0, 100 - linked_prs × 30) |
| Complexity match | 15% | 100-300 word body=100, <100=40, >500=60 |

## Fit Score (max 100 points)

| Signal | Weight | Calculation |
|---|---|---|
| Language match | 30% | Primary lang in user's skills = 100, secondary = 60 |
| Framework match | 40% | Repo topics/desc match user frameworks (fuzzy) |
| Skill-level match | 30% | Issue complexity vs user experience level |

## Implementation

The rank_opportunities.py script implements this formula. Each repo/issue
pair gets a composite score. Results are sorted descending. Top 10 are
"recommended", issues ranked 11-15 are "long-shot high-reward".
