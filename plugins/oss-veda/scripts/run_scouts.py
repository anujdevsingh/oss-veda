#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
#   "pydantic>=2.0",
# ]
# ///
"""Orchestrator — runs all 5 scouts in parallel and merges results."""

import asyncio
import json
import os
import re
import sys
import argparse
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone

# Add scripts dir to path so we can import scout modules
sys.path.insert(0, str(Path(__file__).parent))

import github_scout
import hn_scout
import reddit_scout
import hf_scout
import pwc_scout

CACHE_DIR = Path(tempfile.gettempdir()) / "oss-veda-cache"
CACHE_TTL = 6 * 3600  # 6 hours
SCOUT_TIMEOUT = 180  # 3 minutes max per scout


def get_cache_path(topic: str, days: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize topic to prevent path traversal
    safe_topic = re.sub(r"[^a-zA-Z0-9_-]", "_", topic)
    return CACHE_DIR / f"scouts_{safe_topic}_{days}d.json"


def is_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return (time.time() - path.stat().st_mtime) < CACHE_TTL
    except OSError:
        return False


async def _run_with_timeout(coro, name: str, timeout: int = SCOUT_TIMEOUT):
    """Wrap a scout coroutine with a timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        print(f"  {name} scout timed out after {timeout}s", file=sys.stderr)
        raise


async def run_all(topic: str, days: int, max_repos: int) -> dict:
    """Run all 5 scouts in parallel with per-scout timeouts."""
    print("Launching 5 parallel scouts...", file=sys.stderr)
    start = datetime.now(timezone.utc)

    results = await asyncio.gather(
        _run_with_timeout(github_scout.run(topic, days, max_repos), "github"),
        _run_with_timeout(hn_scout.run(f"{topic} OR LLM OR machine learning"), "hackernews"),
        _run_with_timeout(reddit_scout.run(), "reddit"),
        _run_with_timeout(hf_scout.run(), "huggingface"),
        _run_with_timeout(pwc_scout.run(), "papers_with_code"),
        return_exceptions=True,
    )

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    scout_names = ["github", "hackernews", "reddit", "huggingface", "papers_with_code"]
    merged = {}
    for name, result in zip(scout_names, results):
        if isinstance(result, Exception):
            err_type = type(result).__name__
            print(f"  {name} scout failed: {err_type}: {str(result)[:100]}", file=sys.stderr)
            merged[name] = []
        else:
            merged[name] = result
            print(f"  {name}: {len(result)} results", file=sys.stderr)

    merged["_metadata"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "days": days,
        "elapsed_seconds": round(elapsed, 1),
        "scouts_succeeded": sum(1 for r in results if not isinstance(r, Exception)),
        "scouts_total": 5,
    }

    print(f"\nAll scouts complete in {elapsed:.1f}s", file=sys.stderr)
    return merged


def main():
    default_output = os.path.join(tempfile.gettempdir(), "oss-veda-raw.json")

    parser = argparse.ArgumentParser(description="oss-veda scout orchestrator")
    parser.add_argument("--topic", default="ai", help="Topic to search (default: ai)")
    parser.add_argument("--days", type=int, default=7, help="Lookback days (default: 7)")
    parser.add_argument("--max-repos", type=int, default=20, help="Max repos from GitHub (default: 20)")
    parser.add_argument("--output", default=default_output, help="Output file path")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache")
    args = parser.parse_args()

    # Check cache
    cache_path = get_cache_path(args.topic, args.days)
    if not args.no_cache and is_cache_fresh(cache_path):
        print("Using cached results (less than 6 hours old)", file=sys.stderr)
        import shutil
        shutil.copy(str(cache_path), args.output)
        try:
            with open(args.output, encoding="utf-8") as f:
                data = json.load(f)
            print(f"Cached results loaded. {data['_metadata']['scouts_succeeded']}/5 scouts.", file=sys.stderr)
        except (json.JSONDecodeError, KeyError):
            print("Cache corrupted, re-running scouts...", file=sys.stderr)
            cache_path.unlink(missing_ok=True)
        else:
            return

    results = asyncio.run(run_all(args.topic, args.days, args.max_repos))

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Write cache
    with open(str(cache_path), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.output}", file=sys.stderr)

    # Log run to history (autoresearch-inspired results.tsv pattern)
    log_run(results)


def log_run(results: dict):
    """Append this run's summary to a TSV history file for tracking over time."""
    history_path = CACHE_DIR / "run_history.tsv"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    meta = results.get("_metadata", {})
    github_count = len(results.get("github", []))
    total_issues = sum(len(r.get("issues", [])) for r in results.get("github", []))
    hn_count = len(results.get("hackernews", []))
    reddit_count = len(results.get("reddit", []))
    hf_count = len(results.get("huggingface", []))
    pwc_count = len(results.get("papers_with_code", []))

    # Write header if file doesn't exist
    if not history_path.exists():
        with open(history_path, "w", encoding="utf-8") as f:
            f.write("timestamp\ttopic\tdays\tscouts_ok\telapsed_s\trepos\tissues\thn\treddit\thf\tpwc\n")

    with open(history_path, "a", encoding="utf-8") as f:
        f.write(
            f"{meta.get('timestamp', '')}\t"
            f"{meta.get('topic', '')}\t"
            f"{meta.get('days', '')}\t"
            f"{meta.get('scouts_succeeded', 0)}/5\t"
            f"{meta.get('elapsed_seconds', '')}\t"
            f"{github_count}\t"
            f"{total_issues}\t"
            f"{hn_count}\t"
            f"{reddit_count}\t"
            f"{hf_count}\t"
            f"{pwc_count}\n"
        )
    print(f"Run logged to {history_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
