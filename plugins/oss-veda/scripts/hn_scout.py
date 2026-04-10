#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
"""Hacker News scout — finds Show HN AI/ML posts with GitHub links."""

import asyncio
import json
import re
import argparse
import sys

import httpx

HN_API = "https://hn.algolia.com/api/v1"


def extract_github_url(text: str) -> str | None:
    """Extract first GitHub repo URL from text."""
    match = re.search(r"https?://github\.com/[\w.\-]+/[\w.\-]+", text or "")
    return match.group(0).rstrip(".") if match else None


async def run(query: str = "AI OR LLM") -> list[dict]:
    """Search HN for Show HN posts about AI/ML projects."""
    results = []
    queries = [query, "open source AI", "machine learning tool"]

    async with httpx.AsyncClient(timeout=20.0) as client:
        for q in queries:
            try:
                resp = await client.get(
                    f"{HN_API}/search",
                    params={
                        "query": q,
                        "tags": "show_hn",
                        "numericFilters": "points>20",
                        "hitsPerPage": 30,
                    },
                )
                resp.raise_for_status()
                for hit in resp.json().get("hits", []):
                    github_url = extract_github_url(hit.get("url", ""))
                    object_id = hit.get("objectID")
                    if github_url and object_id:
                        results.append({
                            "source": "hackernews",
                            "title": hit.get("title", ""),
                            "github_url": github_url,
                            "hn_url": f"https://news.ycombinator.com/item?id={object_id}",
                            "points": hit.get("points", 0),
                            "comments": hit.get("num_comments", 0),
                            "created_at": hit.get("created_at", ""),
                        })
            except httpx.HTTPError as e:
                print(f"Warning: HN search failed for '{q}': {e}", file=sys.stderr)

    # Deduplicate by github_url
    seen = set()
    unique = []
    for r in results:
        if r["github_url"] not in seen:
            seen.add(r["github_url"])
            unique.append(r)
    return unique


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HN Scout for oss-veda")
    parser.add_argument("--query", default="AI OR LLM")
    args = parser.parse_args()

    results = asyncio.run(run(args.query))
    print(json.dumps(results, indent=2))
