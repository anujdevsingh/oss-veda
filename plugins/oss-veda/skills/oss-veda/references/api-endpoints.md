# API Endpoints Reference

## GitHub REST API

Base URL: https://api.github.com
Auth: Bearer token via GITHUB_TOKEN env var
Rate limit: 5,000 req/hr authenticated, 30/min for search

### Search trending repos
```
GET /search/repositories?q=topic:{topic}+stars:>{min_stars}+created:>{since_date}&sort=stars&order=desc&per_page=20
```

### Search issues by label
```
GET /search/issues?q=repo:{full_name}+label:"good first issue"+state:open&sort=created&order=desc&per_page=5
```

### Combine labels with OR (comma = OR)
```
GET /search/issues?q=label:"good first issue","help wanted"+state:open+topic:llm+language:python&sort=reactions-+1&order=desc
```

### Star velocity (stargazers with timestamps)
```
GET /repos/{owner}/{repo}/stargazers
Headers: Accept: application/vnd.github.v3.star+json
```
Returns starred_at timestamps. Sample last 3-5 pages for recent velocity.

### Repo community health
```
GET /repos/{owner}/{repo}/community/profile
```

### Recent PRs (for merge rate)
```
GET /repos/{owner}/{repo}/pulls?state=closed&per_page=30
```

## Hacker News Algolia API

Base URL: https://hn.algolia.com/api/v1
Auth: None required
Rate limit: 10,000 req/hr

### Search Show HN posts
```
GET /search?query={query}&tags=show_hn&numericFilters=points>20&hitsPerPage=30
```

### Front page stories
```
GET /search?tags=front_page&query={query}&hitsPerPage=20
```

## Reddit Public JSON

Base URL: https://www.reddit.com
Auth: User-Agent header required, no OAuth for public .json endpoints
Rate limit: ~10 requests/minute for public .json

### Subreddit top posts
```
GET /r/{subreddit}/top.json?t=week&limit=25
```

### Search within subreddit
```
GET /r/{subreddit}/search.json?q=github.com&sort=top&t=month&restrict_sr=on
```

Key subreddits: MachineLearning, LocalLLaMA, LangChain

## HuggingFace API

Base URL: https://huggingface.co/api
Auth: Optional for public data
Rate limit: Generous, undocumented

### Trending models
```
GET /models?sort=trending_score&direction=-1&limit=20
```

### Trending Spaces
```
GET /spaces?sort=trending_score&direction=-1&limit=20
```

## Papers with Code

Base URL: https://paperswithcode.com/api/v1
Auth: None required
Rate limit: Generous

### Search papers
```
GET /search/?q={query}
```

### List repos by stars
```
GET /repos/?stars_lower_bound=500&framework=pytorch
```

## OSS Insight (fallback for GitHub rate limits)

Base URL: https://api.ossinsight.io/v1
Auth: None required

### Trending repos
```
GET /trends/repos/?period=past_week&language=Python
```
