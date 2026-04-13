#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
#   "pydantic>=2.0",
# ]
# ///
"""GitHub scout — finds trending AI/ML repos with good-first-issues."""

import asyncio
import os
import json
import argparse
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
SEARCH_DELAY = 2.2  # seconds between search API calls (30/min limit)
CACHE_DIR = Path(tempfile.gettempdir()) / "oss-veda-cache"
CACHE_TTL = 6 * 3600

# Top 12 highest-signal AI/ML topics (trimmed from 30 to avoid rate limits)
AI_ML_TOPICS = [
    "llm", "langchain", "langgraph", "rag",
    "agents", "ai-agents", "pytorch", "transformers",
    "huggingface", "fine-tuning", "vllm", "mlops",
]


class Issue(BaseModel):
    title: str
    url: str
    labels: list[str]
    body_excerpt: str
    created_at: str
    comments: int
    has_assignee: bool


class RepoResult(BaseModel):
    full_name: str
    url: str
    stars: int
    description: Optional[str]
    topics: list[str]
    language: Optional[str]
    created_at: str
    pushed_at: str
    open_issues_count: int
    forks: int
    issues: list[Issue]


async def _request_with_backoff(
    client: httpx.AsyncClient, url: str, params: dict, max_retries: int = 2
) -> httpx.Response | None:
    """Make a request with exponential backoff on 403/429."""
    for attempt in range(max_retries + 1):
        try:
            resp = await client.get(url, headers=HEADERS, params=params)
            if resp.status_code in (403, 429):
                if attempt < max_retries:
                    # Check Retry-After header (can be seconds or HTTP-date), fallback to exponential backoff
                    retry_header = resp.headers.get("Retry-After", "")
                    try:
                        retry_after = int(retry_header) if retry_header else 0
                    except ValueError:
                        # HTTP-date format — parse and compute delta
                        from email.utils import parsedate_to_datetime
                        try:
                            retry_dt = parsedate_to_datetime(retry_header)
                            retry_after = max(0, int((retry_dt - datetime.now(timezone.utc)).total_seconds()))
                        except (ValueError, TypeError):
                            retry_after = 0
                    wait = max(retry_after, 5 * (2 ** attempt))
                    print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1})...", file=sys.stderr)
                    await asyncio.sleep(wait)
                    continue
                else:
                    print(f"  Rate limit exceeded after {max_retries + 1} attempts, skipping.", file=sys.stderr)
                    return None
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as e:
            if attempt < max_retries:
                await asyncio.sleep(3 * (2 ** attempt))
                continue
            print(f"Warning: Request failed after retries: {e}", file=sys.stderr)
            return None
    return None


async def search_repos(
    client: httpx.AsyncClient, topic: str, days: int, min_stars: int = 50,
    focus_areas: list[str] | None = None,
) -> list[dict]:
    """Search GitHub for trending AI/ML repos across focused subtopics."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    results = []

    # Build query list: user topic + focused subtopics (profile-aware)
    subtopics = focus_areas if focus_areas is not None else AI_ML_TOPICS
    queries = [topic]
    for subtopic in subtopics:
        if subtopic != topic:
            queries.append(subtopic)

    for query_topic in queries:
        resp = await _request_with_backoff(
            client,
            "https://api.github.com/search/repositories",
            params={
                "q": f"topic:{query_topic} stars:>{min_stars} pushed:>{since}",
                "sort": "stars",
                "order": "desc",
                "per_page": 15,
            },
        )
        if resp:
            results.extend(resp.json().get("items", []))
        await asyncio.sleep(SEARCH_DELAY)

    # Deduplicate by full_name
    seen = set()
    unique = []
    for r in results:
        if r["full_name"] not in seen:
            seen.add(r["full_name"])
            unique.append(r)
    return unique


async def fetch_issues(
    client: httpx.AsyncClient, full_name: str
) -> list[Issue]:
    """Fetch contributable issues for a repo."""
    issues = []
    seen_urls = set()

    for label in ["good first issue", "help wanted"]:
        resp = await _request_with_backoff(
            client,
            "https://api.github.com/search/issues",
            params={
                "q": f'repo:{full_name} label:"{label}" state:open no:assignee',
                "sort": "created",
                "order": "desc",
                "per_page": 10,
            },
        )
        if resp and resp.status_code == 200:
            for item in resp.json().get("items", []):
                url = item["html_url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                issues.append(
                    Issue(
                        title=item["title"],
                        url=url,
                        labels=[lbl["name"] for lbl in item["labels"]],
                        body_excerpt=(item.get("body") or "")[:300],
                        created_at=item.get("created_at", ""),
                        comments=item.get("comments", 0),
                        has_assignee=bool(item.get("assignee")),
                    )
                )
        await asyncio.sleep(SEARCH_DELAY)

    # Fallback: recent bugs/enhancements if few issues found
    if len(issues) < 3:
        since_90d = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
        for label in ["bug", "enhancement"]:
            resp = await _request_with_backoff(
                client,
                "https://api.github.com/search/issues",
                params={
                    "q": f'repo:{full_name} label:"{label}" state:open created:>{since_90d} no:assignee',
                    "sort": "created",
                    "order": "desc",
                    "per_page": 5,
                },
            )
            if resp and resp.status_code == 200:
                for item in resp.json().get("items", []):
                    url = item["html_url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    issues.append(
                        Issue(
                            title=item["title"],
                            url=url,
                            labels=[lbl["name"] for lbl in item["labels"]],
                            body_excerpt=(item.get("body") or "")[:300],
                            created_at=item.get("created_at", ""),
                            comments=item.get("comments", 0),
                            has_assignee=bool(item.get("assignee")),
                        )
                    )
            await asyncio.sleep(SEARCH_DELAY)

    return issues


async def global_issue_search(
    client: httpx.AsyncClient, days: int,
    user_languages: list[str] | None = None,
) -> list[dict]:
    """Search GitHub globally for good-first-issues in AI/ML repos."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    results = []
    seen_urls = set()

    if user_languages is not None:
        # Build language-specific queries from user's languages (cap at 4)
        langs = user_languages[:4]
        queries = [
            f'label:"good first issue" language:{lang} topic:ai state:open created:>{since}'
            for lang in langs
        ]
    else:
        queries = [
            f'label:"good first issue" language:python topic:llm state:open created:>{since}',
            f'label:"good first issue" language:python topic:machine-learning state:open created:>{since}',
            f'label:"help wanted" language:python topic:ai state:open created:>{since}',
            f'label:"good first issue" language:typescript topic:ai state:open created:>{since}',
        ]

    for query in queries:
        resp = await _request_with_backoff(
            client,
            "https://api.github.com/search/issues",
            params={"q": query, "sort": "created", "order": "desc", "per_page": 15},
        )
        if resp and resp.status_code == 200:
            for item in resp.json().get("items", []):
                url = item["html_url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                # Parse repo full_name from repository_url
                parsed = urlparse(item["repository_url"])
                path_parts = parsed.path.strip("/").split("/")
                full_name = f"{path_parts[-2]}/{path_parts[-1]}" if len(path_parts) >= 2 else ""
                if not full_name:
                    continue
                results.append({
                    "issue": Issue(
                        title=item["title"],
                        url=url,
                        labels=[lbl["name"] for lbl in item["labels"]],
                        body_excerpt=(item.get("body") or "")[:300],
                        created_at=item.get("created_at", ""),
                        comments=item.get("comments", 0),
                        has_assignee=bool(item.get("assignee")),
                    ),
                    "repo_full_name": full_name,
                    "repo_api_url": item["repository_url"],
                })
        await asyncio.sleep(SEARCH_DELAY)

    return results


async def enrich_repo(client: httpx.AsyncClient, api_url: str) -> dict | None:
    """Fetch repo details from API URL."""
    resp = await _request_with_backoff(client, api_url, params={})
    if resp and resp.status_code == 200:
        return resp.json()
    return None


async def run(
    topic: str = "ai", days: int = 7, max_repos: int = 20,
    focus_areas: list[str] | None = None,
    user_languages: list[str] | None = None,
) -> list[dict]:
    """Main entry point — returns list of repo dicts with issues."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        if not GITHUB_TOKEN:
            print("Warning: GITHUB_TOKEN not set. Rate limits will be very low.", file=sys.stderr)

        # Strategy 1: Search trending repos, then find issues in them
        repos = await search_repos(client, topic, days, focus_areas=focus_areas)
        repos = repos[:max_repos]

        tasks = [fetch_issues(client, r["full_name"]) for r in repos]
        all_issues = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        seen_repos = set()
        for repo, issues in zip(repos, all_issues):
            if isinstance(issues, Exception):
                print(f"  Warning: issue fetch failed for {repo['full_name']}: {type(issues).__name__}", file=sys.stderr)
                issues = []
            seen_repos.add(repo["full_name"])
            results.append(
                RepoResult(
                    full_name=repo["full_name"],
                    url=repo["html_url"],
                    stars=repo.get("stargazers_count", 0),
                    description=repo.get("description"),
                    topics=repo.get("topics", []),
                    language=repo.get("language"),
                    created_at=repo.get("created_at", ""),
                    pushed_at=repo.get("pushed_at", ""),
                    open_issues_count=repo.get("open_issues_count", 0),
                    forks=repo.get("forks_count", 0),
                    issues=issues,
                ).model_dump()
            )

        # Strategy 2: Search globally for AI/ML good-first-issues
        print("  Searching global issues...", file=sys.stderr)
        global_issues = await global_issue_search(client, days=max(days * 4, 30), user_languages=user_languages)

        # Group by repo and enrich repos we haven't seen yet
        repo_issues_map: dict[str, list] = {}
        repo_api_urls: dict[str, str] = {}
        for gi in global_issues:
            fn = gi["repo_full_name"]
            if fn in seen_repos:
                continue
            repo_issues_map.setdefault(fn, []).append(gi["issue"])
            repo_api_urls[fn] = gi["repo_api_url"]

        # Fetch repo details for new repos
        enrich_tasks = [enrich_repo(client, url) for url in repo_api_urls.values()]
        enriched = await asyncio.gather(*enrich_tasks, return_exceptions=True)

        for (fn, api_url), repo_data in zip(repo_api_urls.items(), enriched):
            if isinstance(repo_data, Exception) or repo_data is None:
                continue
            issues = repo_issues_map.get(fn, [])
            results.append(
                RepoResult(
                    full_name=repo_data["full_name"],
                    url=repo_data["html_url"],
                    stars=repo_data.get("stargazers_count", 0),
                    description=repo_data.get("description"),
                    topics=repo_data.get("topics", []),
                    language=repo_data.get("language"),
                    created_at=repo_data.get("created_at", ""),
                    pushed_at=repo_data.get("pushed_at", ""),
                    open_issues_count=repo_data.get("open_issues_count", 0),
                    forks=repo_data.get("forks_count", 0),
                    issues=issues,
                ).model_dump()
            )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub Scout for oss-veda")
    parser.add_argument("--topic", default="ai")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-repos", type=int, default=20)
    args = parser.parse_args()

    results = asyncio.run(run(args.topic, args.days, args.max_repos))
    print(json.dumps(results, indent=2))
