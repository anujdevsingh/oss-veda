#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
"""Reddit scout — finds trending AI/ML repos from subreddits."""

import asyncio
import json
import re
import sys

import httpx

SUBREDDITS = ["MachineLearning", "LocalLLaMA", "LangChain"]
USER_AGENT = "oss-veda/1.0 (https://github.com/anujdevsingh/anuj-ai-tools)"


def extract_github_url(text: str) -> str | None:
    match = re.search(r"https?://github\.com/[\w.\-]+/[\w.\-]+", text or "")
    return match.group(0).rstrip(".") if match else None


async def run() -> list[dict]:
    results = []
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}) as client:
        for sub in SUBREDDITS:
            try:
                resp = await client.get(
                    f"https://www.reddit.com/r/{sub}/top.json",
                    params={"t": "week", "limit": 25},
                )
                if resp.status_code != 200:
                    continue
                try:
                    posts = resp.json().get("data", {}).get("children", [])
                except json.JSONDecodeError:
                    print(f"Warning: Reddit r/{sub} returned invalid JSON", file=sys.stderr)
                    continue
                for post in posts:
                    data = post.get("data", {})
                    github_url = extract_github_url(data.get("url", ""))
                    if not github_url:
                        github_url = extract_github_url(data.get("selftext", ""))
                    if github_url:
                        results.append({
                            "source": "reddit",
                            "subreddit": sub,
                            "title": data.get("title", ""),
                            "github_url": github_url,
                            "reddit_url": f"https://www.reddit.com{data.get('permalink', '')}",
                            "score": data.get("score", 0),
                            "comments": data.get("num_comments", 0),
                        })
                await asyncio.sleep(1.5)  # Rate limit
            except httpx.HTTPError as e:
                print(f"Warning: Reddit r/{sub} failed: {e}", file=sys.stderr)

    seen = set()
    unique = []
    for r in results:
        if r["github_url"] not in seen:
            seen.add(r["github_url"])
            unique.append(r)
    return unique


if __name__ == "__main__":
    results = asyncio.run(run())
    print(json.dumps(results, indent=2))
