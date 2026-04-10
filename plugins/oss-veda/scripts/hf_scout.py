#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
"""HuggingFace scout — finds trending models and Spaces."""

import asyncio
import json
import sys

import httpx

HF_API = "https://huggingface.co/api"


async def run() -> list[dict]:
    results = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for endpoint in ["models", "spaces"]:
            try:
                resp = await client.get(
                    f"{HF_API}/{endpoint}",
                    params={"sort": "trendingScore", "direction": "-1", "limit": "20"},
                )
                resp.raise_for_status()
                for item in resp.json():
                    # HuggingFace URLs use the ID directly (e.g. huggingface.co/meta-llama/Llama-2)
                    results.append({
                        "source": f"huggingface_{endpoint}",
                        "id": item.get("id", ""),
                        "url": f"https://huggingface.co/{item.get('id', '')}",
                        "downloads": item.get("downloads", 0),
                        "likes": item.get("likes", 0),
                        "tags": item.get("tags", [])[:10],
                        "created_at": item.get("createdAt", ""),
                    })
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                print(f"Warning: HuggingFace {endpoint} failed: {e}", file=sys.stderr)
    return results


if __name__ == "__main__":
    results = asyncio.run(run())
    print(json.dumps(results, indent=2))
