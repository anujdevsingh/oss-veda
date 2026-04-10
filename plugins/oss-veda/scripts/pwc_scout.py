#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
"""Papers with Code scout — finds trending papers with linked repos."""

import asyncio
import json
import sys

import httpx

PWC_API = "https://paperswithcode.com/api/v1"


async def run() -> list[dict]:
    results = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for query in ["large language model", "AI agents", "fine-tuning"]:
            try:
                resp = await client.get(
                    f"{PWC_API}/search/",
                    params={"q": query},
                )
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "application/json" not in content_type:
                    print(f"Warning: PwC returned non-JSON for '{query}', API may be unavailable", file=sys.stderr)
                    continue
                for item in resp.json().get("results", [])[:10]:
                    paper = item.get("paper", {})
                    repos = item.get("repositories", [])
                    if repos:
                        results.append({
                            "source": "papers_with_code",
                            "title": paper.get("title", ""),
                            "paper_url": paper.get("url_abs", ""),
                            "github_url": repos[0].get("url", "") if repos else "",
                            "stars": repos[0].get("stars", 0) if repos else 0,
                            "framework": repos[0].get("framework", "") if repos else "",
                        })
            except httpx.HTTPError as e:
                print(f"Warning: PwC search failed for '{query}': {e}", file=sys.stderr)

    seen = set()
    unique = []
    for r in results:
        if r.get("github_url") and r["github_url"] not in seen:
            seen.add(r["github_url"])
            unique.append(r)
    return unique


if __name__ == "__main__":
    results = asyncio.run(run())
    print(json.dumps(results, indent=2))
