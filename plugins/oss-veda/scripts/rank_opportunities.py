#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Rank opportunities by career-impact score."""

import json
import math
import argparse
import sys
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --- Resolve config ---
SCRIPT_DIR = Path(__file__).parent
PLUGIN_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = PLUGIN_ROOT / "config.json"

# Load config if it exists, otherwise use defaults
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        CONFIG = json.load(f)
else:
    CONFIG = {}

SKILL_PROFILE = CONFIG.get("skill_profile", {
    "languages": {"python": 1.0, "typescript": 0.7, "javascript": 0.5},
    "frameworks": {
        "pytorch": 0.9, "crewai": 0.95, "langgraph": 0.85,
        "langchain": 0.8, "nextjs": 0.7, "fastapi": 0.7,
        "huggingface": 0.85, "qlora": 0.9, "rag": 0.9,
        "gemma": 0.9, "gcp": 0.7, "vllm": 0.5,
        "transformers": 0.85, "peft": 0.9, "agents": 0.9,
    },
})

SCORING = CONFIG.get("scoring", {
    "freshness_half_life_days": 30,
    "repo_weight": 0.40,
    "issue_weight": 0.35,
    "fit_weight": 0.25,
    "top_n": 20,
    "long_shot_n": 5,
})


def score_repo(repo: dict, social_signals: dict) -> float:
    """Score a repo (0-100) based on momentum and visibility."""
    stars = repo.get("stars", 0)
    forks = repo.get("forks", 0)

    # Star score: logarithmic scale so small fast-growing repos compete with giants
    # 100 stars = 33, 1000 = 50, 10000 = 67, 100000 = 83
    star_score = min(math.log10(max(stars, 1)) / 6 * 100, 100)

    # Fork-to-star ratio: healthy repos have 10-30% fork ratio
    fork_ratio = forks / max(stars, 1)
    if 0.05 <= fork_ratio <= 0.4:
        community_health = 80
    elif fork_ratio > 0.4:
        community_health = 60  # too many forks, possibly abandoned
    else:
        community_health = 40  # very few forks

    # Social buzz from HN + Reddit + HuggingFace
    social_points = social_signals.get(repo.get("full_name", ""), 0)
    social_score = min(math.log10(max(social_points, 1)) / 3 * 100, 100) if social_points > 0 else 0

    # Recently pushed = actively maintained
    pushed_at = repo.get("pushed_at", "")
    push_recency = 50  # default
    if pushed_at:
        try:
            pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_since_push = (datetime.now(timezone.utc) - pushed_dt).days
            if days_since_push <= 1:
                push_recency = 100
            elif days_since_push <= 7:
                push_recency = 85
            elif days_since_push <= 30:
                push_recency = 60
            else:
                push_recency = 30
        except (ValueError, TypeError):
            pass

    return (
        0.25 * star_score
        + 0.20 * social_score
        + 0.20 * community_health
        + 0.20 * push_recency
        + 0.15 * 65  # PR merge rate placeholder (needs API data)
    )


def score_issue(issue: dict) -> float:
    """Score an issue (0-100) based on quality signals.
    Returns -1 for issues that should be skipped entirely."""
    if issue.get("has_assignee"):
        return -1

    labels = [l.lower() for l in issue.get("labels", [])]

    # Label scoring: multiple good labels stack (capped at 100)
    label_score = 30  # base for unlabeled
    label_bonuses = {
        "good first issue": 40, "help wanted": 30, "bug": 25,
        "enhancement": 20, "feature": 20, "documentation": 15,
        "hacktoberfest": 10,
    }
    for label, bonus in label_bonuses.items():
        if label in labels:
            label_score += bonus
    label_score = min(label_score, 100)

    # Freshness: exponential decay with configurable half-life
    created = issue.get("created_at", "")
    days_old = 30  # default
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_old = max(0, (datetime.now(timezone.utc) - created_dt).days)
        except (ValueError, TypeError):
            pass
    half_life = SCORING.get("freshness_half_life_days", 30)
    freshness = max(0, 100 * math.exp(-0.693 * days_old / half_life))

    # Engagement: sweet spot is 1-8 comments (maintainer engaged, not a rathole)
    comments = issue.get("comments", 0)
    if comments == 0:
        engagement = 30  # no signal yet
    elif 1 <= comments <= 3:
        engagement = 100  # ideal: maintainer responded, few participants
    elif 4 <= comments <= 8:
        engagement = 80  # active discussion, still approachable
    elif 9 <= comments <= 15:
        engagement = 50  # getting crowded
    else:
        engagement = 20  # likely stuck or contentious

    # Competition: open issues with no assignee and few comments = low competition
    competition = 80
    if comments == 0 and not issue.get("has_assignee"):
        competition = 95  # wide open

    # Complexity: check for structure in body, not just length
    body = issue.get("body_excerpt", "")
    body_len = len(body)
    body_lower = body.lower()
    # Structural signals: steps, expected behavior, checkboxes
    has_structure = any(kw in body_lower for kw in [
        "steps to reproduce", "expected", "actual", "- [ ]",
        "acceptance criteria", "todo", "checklist",
    ])
    if has_structure and 80 <= body_len <= 300:
        complexity = 100  # clear, well-structured, right size
    elif 80 <= body_len <= 300:
        complexity = 85  # good length even without structure keywords
    elif body_len < 50:
        complexity = 30  # too vague
    elif body_len < 80:
        complexity = 55  # brief but might be clear
    else:
        complexity = 65  # long, might be complex but at least detailed

    return (
        0.25 * label_score
        + 0.25 * freshness
        + 0.20 * engagement
        + 0.15 * competition
        + 0.15 * complexity
    )


def score_fit(repo: dict) -> float:
    """Score skill fit (0-100) based on user profile.
    Uses soft scoring -- never hard-filters, just scores low for poor fit."""
    lang = (repo.get("language") or "").lower()

    # Soft language scoring: unknown/unfamiliar languages get low score, not -1
    lang_proficiency = SKILL_PROFILE.get("languages", {}).get(lang, 0)
    if lang_proficiency > 0:
        lang_score = lang_proficiency * 100
    elif lang == "" or lang is None:
        lang_score = 50  # unknown language, could be anything
    else:
        # Language not in profile: low score but not excluded
        # Some repos (e.g. Rust tokenizers) have Python issues
        lang_score = 15

    topics = [t.lower() for t in repo.get("topics", [])]
    desc = (repo.get("description") or "").lower()
    all_text = " ".join(topics) + " " + desc

    frameworks = SKILL_PROFILE.get("frameworks", {})
    framework_matches = [v for k, v in frameworks.items() if k in all_text]
    if framework_matches:
        framework_score = (sum(framework_matches) / len(framework_matches)) * 100
    else:
        framework_score = 25  # no framework match

    return 0.30 * lang_score + 0.40 * framework_score + 0.30 * 70


def build_social_map(data: dict) -> dict:
    """Build a map of repo full_name -> social signal score from all sources."""
    social = {}

    # HN + Reddit signals
    for source in ["hackernews", "reddit"]:
        for item in data.get(source, []):
            url = item.get("github_url", "")
            parts = url.replace("https://github.com/", "").split("/")
            if len(parts) >= 2:
                full_name = f"{parts[0]}/{parts[1]}"
                points = item.get("points", 0) + item.get("score", 0)
                social[full_name] = social.get(full_name, 0) + points

    # HuggingFace signals: map HF model/space IDs to GitHub repos if possible
    for item in data.get("huggingface", []):
        likes = item.get("likes", 0)
        downloads = item.get("downloads", 0)
        # Normalize: 1000 likes ~ 100 HN points, 100k downloads ~ 50 points
        hf_score = min(likes / 10, 100) + min(downloads / 2000, 50)
        hf_id = item.get("id", "")
        if "/" in hf_id:
            org = hf_id.split("/")[0]
            # Try to match org to GitHub repos in the data
            for repo in data.get("github", []):
                repo_name = repo.get("full_name", "").lower()
                if org.lower() in repo_name:
                    social[repo.get("full_name", "")] = social.get(repo.get("full_name", ""), 0) + hf_score

    return social


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(tempfile.gettempdir(), "oss-veda-raw.json"))
    parser.add_argument("--output", default=os.path.join(tempfile.gettempdir(), "oss-veda-ranked.json"))
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    social_map = build_social_map(data)
    ranked = []

    repo_weight = SCORING.get("repo_weight", 0.40)
    issue_weight = SCORING.get("issue_weight", 0.35)
    fit_weight = SCORING.get("fit_weight", 0.25)

    skipped = 0
    for repo in data.get("github", []):
        fit = score_fit(repo)
        repo_score = score_repo(repo, social_map)

        for issue in repo.get("issues", []):
            issue_score = score_issue(issue)
            if issue_score == -1:
                skipped += 1
                continue  # assigned issue
            career_impact = repo_weight * repo_score + issue_weight * issue_score + fit_weight * fit

            ranked.append({
                "career_impact_score": round(career_impact, 1),
                "repo_score": round(repo_score, 1),
                "issue_score": round(issue_score, 1),
                "fit_score": round(fit, 1),
                "repo": {
                    "full_name": repo.get("full_name", ""),
                    "url": repo.get("url", ""),
                    "stars": repo.get("stars", 0),
                    "description": repo.get("description", ""),
                    "topics": repo.get("topics", []),
                    "language": repo.get("language", ""),
                },
                "issue": {
                    "title": issue.get("title", ""),
                    "url": issue.get("url", ""),
                    "labels": issue.get("labels", []),
                    "body_excerpt": issue.get("body_excerpt", ""),
                },
                "social_signals": {
                    "full_name": repo.get("full_name", ""),
                    "social_score": social_map.get(repo.get("full_name", ""), 0),
                },
            })

    ranked.sort(key=lambda x: x["career_impact_score"], reverse=True)

    top_n = SCORING.get("top_n", 20)
    long_n = SCORING.get("long_shot_n", 5)
    output = {
        "ranked_opportunities": ranked[:top_n],
        "long_shots": ranked[top_n:top_n + long_n] if len(ranked) > top_n else [],
        "total_scored": len(ranked),
        "total_skipped": skipped,
        "metadata": data.get("_metadata", {}),
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\u2705 Ranked {len(ranked)} opportunities ({skipped} skipped). "
          f"Top {min(top_n, len(ranked))} + {len(output['long_shots'])} long-shots saved.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
