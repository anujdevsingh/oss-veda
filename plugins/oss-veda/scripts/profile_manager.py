#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""oss-veda profile manager — CRUD operations for user profile data."""

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(tempfile.gettempdir()) / "oss-veda-cache"
PROFILE_PATH = CACHE_DIR / "user-profile.json"
SESSION_PATH = CACHE_DIR / "user-profile-session.json"

REQUIRED_FIELDS = {
    "languages",
    "frameworks",
    "experience_level",
    "contribution_preferences",
    "focus_areas",
}
VALID_EXPERIENCE_LEVELS = {"student", "early_career", "mid_level", "senior"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _load_profile(path: Path) -> dict | None:
    """Load and parse a JSON profile file. Returns None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _ensure_cache_dir() -> None:
    """Create the cache directory if it does not exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Mode: check
# ---------------------------------------------------------------------------

def mode_check() -> None:
    """Print profile existence and metadata as JSON."""
    profile = _load_profile(PROFILE_PATH)

    if profile is None:
        json.dump({"exists": False}, sys.stdout)
        sys.stdout.write("\n")
        return

    age_days: float | None = None
    updated_at = profile.get("updated_at") or profile.get("created_at")
    if updated_at:
        try:
            ts = datetime.fromisoformat(updated_at)
            # Ensure tz-aware for subtraction
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - ts
            age_days = round(delta.total_seconds() / 86400, 1)
        except (ValueError, TypeError):
            pass

    result: dict = {"exists": True, "profile": profile}
    if age_days is not None:
        result["age_days"] = age_days

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Mode: save
# ---------------------------------------------------------------------------

def mode_save(data_str: str | None) -> None:
    """Validate and write a profile to PROFILE_PATH."""
    if not data_str:
        print(json.dumps({"error": "--data is required for save mode"}), file=sys.stderr)
        sys.exit(1)

    try:
        incoming: dict = json.loads(data_str)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON in --data: {exc}"}), file=sys.stderr)
        sys.exit(1)

    # Validate required fields
    missing = REQUIRED_FIELDS - set(incoming.keys())
    if missing:
        print(
            json.dumps({"error": f"Missing required fields: {sorted(missing)}"}),
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate experience_level
    exp = incoming.get("experience_level")
    if exp not in VALID_EXPERIENCE_LEVELS:
        print(
            json.dumps({
                "error": (
                    f"Invalid experience_level '{exp}'. "
                    f"Must be one of: {sorted(VALID_EXPERIENCE_LEVELS)}"
                )
            }),
            file=sys.stderr,
        )
        sys.exit(1)

    # Preserve created_at if updating an existing profile
    existing = _load_profile(PROFILE_PATH)
    if existing and "created_at" in existing:
        incoming.setdefault("created_at", existing["created_at"])
    else:
        incoming.setdefault("created_at", _now_iso())

    incoming["updated_at"] = _now_iso()
    incoming.setdefault("version", 1)

    _ensure_cache_dir()
    PROFILE_PATH.write_text(json.dumps(incoming, indent=2) + "\n", encoding="utf-8")

    json.dump({"saved": True, "path": str(PROFILE_PATH)}, sys.stdout)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Mode: merge
# ---------------------------------------------------------------------------

def mode_merge(data_str: str | None) -> None:
    """Merge overrides into the saved profile and write to SESSION_PATH."""
    saved = _load_profile(PROFILE_PATH)
    if saved is None:
        print(
            json.dumps({"error": "No saved profile found. Run --mode save first."}),
            file=sys.stderr,
        )
        sys.exit(1)

    if not data_str:
        # No overrides — copy saved profile directly to session file
        _ensure_cache_dir()
        SESSION_PATH.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        json.dump({"merged": True, "path": str(SESSION_PATH)}, sys.stdout)
        sys.stdout.write("\n")
        return

    try:
        overrides: dict = json.loads(data_str)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON in --data: {exc}"}), file=sys.stderr)
        sys.exit(1)

    # Merge: top-level keys replaced; dict values merged via .update()
    merged = dict(saved)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = dict(merged[key])
            merged[key].update(value)
        else:
            merged[key] = value

    _ensure_cache_dir()
    SESSION_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    json.dump({"merged": True, "path": str(SESSION_PATH)}, sys.stdout)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Mode: cleanup
# ---------------------------------------------------------------------------

def mode_cleanup() -> None:
    """Delete SESSION_PATH only. Never touches the saved profile."""
    try:
        SESSION_PATH.unlink(missing_ok=True)
    except OSError:
        pass  # silent on errors

    json.dump({"cleaned": True}, sys.stdout)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="oss-veda profile manager — CRUD for user profile data."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["check", "save", "merge", "cleanup"],
        help="Operation mode.",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="JSON string payload (required for save; optional for merge).",
    )
    args = parser.parse_args()

    if args.mode == "check":
        mode_check()
    elif args.mode == "save":
        mode_save(args.data)
    elif args.mode == "merge":
        mode_merge(args.data)
    elif args.mode == "cleanup":
        mode_cleanup()


if __name__ == "__main__":
    main()
