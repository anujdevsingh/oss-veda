#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""oss-veda guard — pre-flight, security, and post-mortem checks."""

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PLUGIN_ROOT = SCRIPT_DIR.parent
CACHE_DIR = Path(tempfile.gettempdir()) / "oss-veda-cache"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_check(check_id: str, name: str, severity: str) -> dict:
    """Return a skeleton result dict."""
    return {
        "id": check_id,
        "name": name,
        "status": "pass",
        "severity": severity,
        "details": "",
        "fix_hint": None,
    }


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

FAILURE_PATTERNS = [
    (r"TimeoutError|timed? ?out", "timeout"),
    (r"403|429|rate.?limit", "rate_limit"),
    (r"ConnectionError|connection.?refused|network", "network"),
    (r"JSONDecodeError|json.*decode|invalid json", "bad_response"),
    (r"KeyError|AttributeError", "api_change"),
]


def classify_failure(error_str: str) -> tuple[str, str, str]:
    """Classify an error string into (category, diagnosis, user_action)."""
    s = str(error_str)
    for pattern, category in FAILURE_PATTERNS:
        if re.search(pattern, s, re.IGNORECASE):
            if category == "timeout":
                return (
                    "timeout",
                    "Scout timed out waiting for API response.",
                    "Check your internet connection and try again; if persistent, the upstream service may be slow.",
                )
            if category == "rate_limit":
                return (
                    "rate_limit",
                    "API rate limit or auth error (HTTP 403/429).",
                    "Wait a few minutes before retrying, or verify your GITHUB_TOKEN is valid and has the right scopes.",
                )
            if category == "network":
                return (
                    "network",
                    "Network connectivity issue.",
                    "Ensure you are online and that api.github.com / other endpoints are reachable.",
                )
            if category == "bad_response":
                return (
                    "bad_response",
                    "Scout received malformed JSON from the upstream API.",
                    "The upstream API may be returning an error page instead of JSON; check service status.",
                )
            if category == "api_change":
                return (
                    "api_change",
                    "Scout encountered a missing key or attribute — the API schema may have changed.",
                    "Update the scout to match the new API response shape.",
                )
    return (
        "unknown",
        f"Unclassified error: {s[:200]}",
        "Check scout logs for details.",
    )


def diagnose_failures(raw_data: dict) -> list[dict]:
    """Return a list of failure dicts for scouts whose data is None (crashed)."""
    scout_names = ["github", "hackernews", "reddit", "huggingface", "papers_with_code"]
    failures = []
    for name in scout_names:
        value = raw_data.get(name)
        if value is None:
            error_str = raw_data.get(f"_error_{name}", "Scout returned None — likely crashed silently.")
            category, diagnosis, user_action = classify_failure(error_str)
            failures.append({
                "scout": name,
                "category": category,
                "diagnosis": diagnosis,
                "user_action": user_action,
                "raw_error": str(error_str)[:500],
            })
    return failures


# ---------------------------------------------------------------------------
# Pre-flight checks (1-7)
# ---------------------------------------------------------------------------

def check_uv_installed() -> dict:
    """Check 1 — uv is installed and callable."""
    result = make_check("1", "uv installed", "hard")
    try:
        proc = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            result["details"] = proc.stdout.strip() or proc.stderr.strip()
        else:
            result["status"] = "fail"
            result["details"] = f"uv exited with code {proc.returncode}"
            result["fix_hint"] = "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
    except FileNotFoundError:
        result["status"] = "fail"
        result["details"] = "'uv' executable not found on PATH."
        result["fix_hint"] = "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
    except subprocess.TimeoutExpired:
        result["status"] = "fail"
        result["details"] = "'uv --version' timed out after 10 seconds."
        result["fix_hint"] = "Check that uv is not hanging; try running 'uv --version' manually."
    return result


def check_python_version() -> dict:
    """Check 2 — Python >= 3.11."""
    result = make_check("2", "Python >= 3.11", "hard")
    vi = sys.version_info
    result["details"] = f"Python {vi.major}.{vi.minor}.{vi.micro}"
    if (vi.major, vi.minor) < (3, 11):
        result["status"] = "fail"
        result["fix_hint"] = "Upgrade to Python 3.11+. With uv: 'uv python install 3.11'."
    return result


def check_temp_dir_writable() -> dict:
    """Check 3 — temp dir / cache dir is writable."""
    result = make_check("3", "Temp dir writable", "hard")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = CACHE_DIR / ".guard_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        result["details"] = f"Cache dir OK: {CACHE_DIR}"
    except OSError as exc:
        result["status"] = "fail"
        result["details"] = f"Cannot write to {CACHE_DIR}: {exc}"
        result["fix_hint"] = f"Ensure the process has write permission to {CACHE_DIR.parent}."
    return result


def check_network_reachable() -> dict:
    """Check 4 — network reachable (api.github.com:443)."""
    result = make_check("4", "Network reachable", "hard")
    try:
        conn = socket.create_connection(("api.github.com", 443), timeout=5)
        conn.close()
        result["details"] = "api.github.com:443 reachable."
    except OSError as exc:
        result["status"] = "fail"
        result["details"] = f"Cannot reach api.github.com:443 — {exc}"
        result["fix_hint"] = "Check your internet connection or firewall settings."
    return result


def check_github_token() -> dict:
    """Check 5 — GITHUB_TOKEN or GH_TOKEN set."""
    result = make_check("5", "GITHUB_TOKEN set", "soft")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        prefix = token[:4]
        result["details"] = f"Token found (starts with '{prefix}...'); source: {'GITHUB_TOKEN' if os.environ.get('GITHUB_TOKEN') else 'GH_TOKEN'}."
    else:
        result["status"] = "warn"
        result["details"] = "Neither GITHUB_TOKEN nor GH_TOKEN is set. GitHub scout will use unauthenticated API (60 req/hr limit)."
        result["fix_hint"] = "Set GITHUB_TOKEN in your shell or .env: export GITHUB_TOKEN=ghp_..."
    return result


def check_plugin_scripts_exist() -> dict:
    """Check 6 — all 9 required plugin scripts exist."""
    result = make_check("6", "Plugin scripts exist", "hard")
    required = [
        "run_scouts.py",
        "github_scout.py",
        "hn_scout.py",
        "reddit_scout.py",
        "hf_scout.py",
        "pwc_scout.py",
        "rank_opportunities.py",
        "generate_report.py",
        "guard.py",
    ]
    missing = [f for f in required if not (SCRIPT_DIR / f).exists()]
    if missing:
        result["status"] = "fail"
        result["details"] = f"Missing scripts: {', '.join(missing)}"
        result["fix_hint"] = "Re-clone or restore the oss-veda plugin repository."
    else:
        result["details"] = f"All {len(required)} scripts present."
    return result


def check_config_json_valid() -> dict:
    """Check 7 — config.json exists and is valid JSON."""
    result = make_check("7", "config.json valid", "soft")
    config_path = PLUGIN_ROOT / "config.json"
    if not config_path.exists():
        result["status"] = "warn"
        result["details"] = "config.json not found; plugin will use built-in defaults."
        result["fix_hint"] = "Create config.json from the example in the plugin README."
        return result
    try:
        with config_path.open() as fh:
            data = json.load(fh)
        keys = list(data.keys()) if isinstance(data, dict) else []
        result["details"] = f"config.json valid JSON with {len(keys)} top-level keys."
    except json.JSONDecodeError as exc:
        result["status"] = "warn"
        result["details"] = f"config.json is invalid JSON: {exc}"
        result["fix_hint"] = "Fix the JSON syntax in config.json (use a linter or jsonlint.com)."
    return result


# ---------------------------------------------------------------------------
# Security checks (8-11)
# ---------------------------------------------------------------------------

def check_cache_dir_size() -> dict:
    """Check 8 — cache dir total size < 100 MB; auto-fix if > 100 MB."""
    result = make_check("8", "Cache dir size sane", "soft")
    LIMIT_BYTES = 100 * 1024 * 1024   # 100 MB warn threshold
    TARGET_BYTES = 80 * 1024 * 1024    # 80 MB target after auto-fix

    if not CACHE_DIR.exists():
        result["details"] = "Cache dir does not exist yet — nothing to check."
        return result

    files = [(f, f.stat().st_size, f.stat().st_mtime) for f in CACHE_DIR.iterdir() if f.is_file()]
    total = sum(size for _, size, _ in files)
    total_mb = total / (1024 * 1024)

    if total <= LIMIT_BYTES:
        result["details"] = f"Cache dir size: {total_mb:.1f} MB (limit 100 MB)."
        return result

    # Auto-fix: delete oldest files until under 80 MB
    files.sort(key=lambda t: t[2])  # oldest first
    deleted = []
    current = total
    for f, size, _ in files:
        if current <= TARGET_BYTES:
            break
        try:
            f.unlink()
            current -= size
            deleted.append(f.name)
        except OSError:
            pass

    after_mb = current / (1024 * 1024)
    result["status"] = "warn"
    result["details"] = (
        f"Cache dir was {total_mb:.1f} MB (> 100 MB limit). "
        f"Auto-deleted {len(deleted)} oldest file(s); now {after_mb:.1f} MB."
    )
    result["fix_hint"] = "Run with --mode preflight regularly to keep cache clean."
    return result


def check_no_unexpected_files() -> dict:
    """Check 9 — no unexpected files in CACHE_DIR."""
    result = make_check("9", "No unexpected files in cache", "soft")

    EXPECTED_PATTERNS = [
        re.compile(r"^scouts_.*\.json$"),
        re.compile(r"^oss-veda-raw\.json$"),
        re.compile(r"^oss-veda-ranked\.json$"),
        re.compile(r"^oss-veda-report\.md$"),
        re.compile(r"^run_history\.tsv$"),
        re.compile(r"^\.guard_write_test$"),
    ]

    if not CACHE_DIR.exists():
        result["details"] = "Cache dir does not exist — nothing to check."
        return result

    unexpected = []
    for f in CACHE_DIR.iterdir():
        if not f.is_file():
            continue
        if not any(p.match(f.name) for p in EXPECTED_PATTERNS):
            unexpected.append(f.name)

    if unexpected:
        result["status"] = "warn"
        result["details"] = f"Unexpected file(s) in cache dir: {', '.join(unexpected)}"
        result["fix_hint"] = f"Review and remove unexpected files from {CACHE_DIR}."
    else:
        result["details"] = "No unexpected files found in cache dir."
    return result


def check_script_checksums() -> dict:
    """Check 10 — SHA256 checksums of scripts match checksums.json."""
    result = make_check("10", "Script checksums match", "hard")
    checksums_path = PLUGIN_ROOT / "checksums.json"

    if not checksums_path.exists():
        # Downgrade to soft warn — guard shouldn't be brittle about its own config
        result["severity"] = "soft"
        result["status"] = "warn"
        result["details"] = "checksums.json not found; skipping integrity check."
        result["fix_hint"] = "Run scripts/_dev_update_checksums.py to generate checksums.json."
        return result

    try:
        with checksums_path.open() as fh:
            stored = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        result["severity"] = "soft"
        result["status"] = "warn"
        result["details"] = f"checksums.json is unreadable or invalid: {exc}"
        result["fix_hint"] = "Run scripts/_dev_update_checksums.py to regenerate checksums.json."
        return result

    mismatches = []
    not_found = []
    file_entries = stored.get("files", {})

    for rel_path, expected_hash in file_entries.items():
        full_path = PLUGIN_ROOT / rel_path
        if not full_path.exists():
            not_found.append(rel_path)
            continue
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            mismatches.append(rel_path)

    issues = []
    if mismatches:
        issues.append(f"hash mismatch: {', '.join(mismatches)}")
    if not_found:
        issues.append(f"files missing: {', '.join(not_found)}")

    if issues:
        result["status"] = "fail"
        result["details"] = "; ".join(issues)
        result["fix_hint"] = (
            "If you intentionally modified scripts, re-run scripts/_dev_update_checksums.py. "
            "Otherwise, restore the original files."
        )
    else:
        result["details"] = f"All {len(file_entries)} checksums verified OK."
    return result


def check_run_history_sane() -> dict:
    """Check 11 — run_history.tsv has correct header; no oversized rows."""
    result = make_check("11", "run_history.tsv sane", "soft")
    history_path = CACHE_DIR / "run_history.tsv"

    EXPECTED_HEADER = "timestamp\tmode\tstatus\tduration_s\tscouts_ok\topportunities"
    MAX_ROW_BYTES = 10 * 1024  # 10 KB

    if not history_path.exists():
        result["details"] = "run_history.tsv does not exist yet — nothing to check."
        return result

    try:
        lines = history_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        result["status"] = "warn"
        result["details"] = f"Cannot read run_history.tsv: {exc}"
        return result

    fixed = False
    issues = []

    # Check / fix header
    if not lines:
        lines = [EXPECTED_HEADER]
        fixed = True
        issues.append("file was empty; wrote header")
    elif lines[0].strip() != EXPECTED_HEADER:
        issues.append(f"bad header: '{lines[0][:80]}'")
        lines[0] = EXPECTED_HEADER
        fixed = True

    # Remove oversized rows (keep header)
    oversized_indices = [
        i for i, line in enumerate(lines[1:], start=1)
        if len(line.encode("utf-8")) > MAX_ROW_BYTES
    ]
    if oversized_indices:
        issues.append(f"removed {len(oversized_indices)} oversized row(s)")
        lines = [line for i, line in enumerate(lines) if i not in oversized_indices]
        fixed = True

    if fixed:
        try:
            history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            result["status"] = "warn"
            result["details"] = f"Auto-fix attempted but could not write: {exc}"
            return result
        result["status"] = "warn"
        result["details"] = f"Auto-fixed run_history.tsv: {'; '.join(issues)}."
        result["fix_hint"] = "run_history.tsv was malformed; the auto-fix should prevent future issues."
    else:
        result["details"] = f"run_history.tsv OK ({len(lines) - 1} data rows)."
    return result


# ---------------------------------------------------------------------------
# Post-mortem checks (12-14)
# ---------------------------------------------------------------------------

def check_scouts_succeeded(raw_data: dict) -> dict:
    """Check 12 — enough scouts succeeded."""
    result = make_check("12", "Scouts succeeded", "soft")
    meta = raw_data.get("_metadata", {})
    n_ok = meta.get("scouts_succeeded", None)

    if n_ok is None:
        result["status"] = "warn"
        result["details"] = "_metadata.scouts_succeeded missing from raw.json."
        result["fix_hint"] = "Ensure run_scouts.py writes _metadata correctly."
        return result

    total = 5
    result["details"] = f"{n_ok}/{total} scouts succeeded."

    if n_ok >= total:
        pass  # all good
    elif n_ok >= 3:
        result["status"] = "warn"
        result["fix_hint"] = "Check individual scout logs for network or API errors."
    else:
        # 0-2 succeeded — hard fail
        result["severity"] = "hard"
        result["status"] = "fail"
        result["fix_hint"] = (
            "Fewer than 3 scouts succeeded. Check GITHUB_TOKEN, network connectivity, "
            "and scout logs."
        )
    return result


def check_report_exists(report_path: Path) -> dict:
    """Check 13 — report file exists and is > 100 bytes."""
    result = make_check("13", "Report file exists", "hard")
    if not report_path.exists():
        result["status"] = "fail"
        result["details"] = f"Report not found at {report_path}."
        result["fix_hint"] = "Run the full oss-veda pipeline (veda-deep or /veda commands)."
        return result

    size = report_path.stat().st_size
    if size <= 100:
        result["status"] = "fail"
        result["details"] = f"Report exists but is only {size} bytes (expected > 100 bytes)."
        result["fix_hint"] = "Report appears empty or truncated; re-run generate_report.py."
    else:
        result["details"] = f"Report found at {report_path} ({size:,} bytes)."
    return result


def check_no_tokens_in_report(report_path: Path) -> dict:
    """Check 14 — no credential patterns leaked into the report."""
    result = make_check("14", "No tokens in report", "hard")

    DANGEROUS_PATTERNS = [
        r"ghp_[A-Za-z0-9_]{36}",       # classic GitHub PAT
        r"github_pat_[A-Za-z0-9_]{82}", # fine-grained PAT
        r"Bearer [A-Za-z0-9\-._~+/]+=*",# Authorization header value
        r"gho_[A-Za-z0-9_]{36}",        # OAuth token
        r"ghu_[A-Za-z0-9_]{36}",        # user-to-server token
    ]

    if not report_path.exists():
        result["status"] = "warn"
        result["details"] = "Report does not exist; cannot scan for tokens."
        result["fix_hint"] = "Ensure the report is generated before running postmortem."
        return result

    try:
        content = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result["status"] = "warn"
        result["details"] = f"Cannot read report: {exc}"
        return result

    found = []
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, content):
            found.append(pattern.split("[")[0])  # show just the prefix hint

    if found:
        result["status"] = "fail"
        result["details"] = f"Potential credential pattern(s) detected: {', '.join(found)}"
        result["fix_hint"] = (
            "Remove all tokens from the report and rotate any exposed credentials immediately. "
            "Check scout code for token logging."
        )
    else:
        result["details"] = "No credential patterns found in report."
    return result


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

def run_preflight() -> dict:
    """Run all 11 pre-flight + security checks and return a result dict."""
    t0 = time.monotonic()

    checks = [
        check_uv_installed(),
        check_python_version(),
        check_temp_dir_writable(),
        check_network_reachable(),
        check_github_token(),
        check_plugin_scripts_exist(),
        check_config_json_valid(),
        check_cache_dir_size(),
        check_no_unexpected_files(),
        check_script_checksums(),
        check_run_history_sane(),
    ]

    n_pass = sum(1 for c in checks if c["status"] == "pass")
    n_warn = sum(1 for c in checks if c["status"] == "warn")
    n_fail = sum(1 for c in checks if c["status"] == "fail")

    has_hard_fail = any(c["status"] == "fail" and c["severity"] == "hard" for c in checks)

    if has_hard_fail:
        overall = "hard_fail"
    elif n_warn > 0 or n_fail > 0:
        overall = "warnings"
    else:
        overall = "ok"

    return {
        "mode": "preflight",
        "status": overall,
        "duration_seconds": round(time.monotonic() - t0, 3),
        "checks": checks,
        "summary": {
            "pass": n_pass,
            "warn": n_warn,
            "fail": n_fail,
            "total": len(checks),
        },
    }


def run_postmortem(input_path: Path) -> dict:
    """Run post-mortem checks on a completed run and return a result dict."""
    t0 = time.monotonic()

    # Load raw.json
    raw_data: dict = {}
    if input_path.exists():
        try:
            raw_data = json.loads(input_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raw_data = {"_load_error": str(exc)}
    else:
        raw_data = {"_load_error": f"File not found: {input_path}"}

    report_path = Path(tempfile.gettempdir()) / "oss-veda-report.md"

    checks = [
        check_scouts_succeeded(raw_data),
        check_report_exists(report_path),
        check_no_tokens_in_report(report_path),
    ]

    failures = diagnose_failures(raw_data)

    meta = raw_data.get("_metadata", {})
    scouts_ok = meta.get("scouts_succeeded", 0)
    scouts_total = 5

    leaked = any(c["id"] == "14" and c["status"] == "fail" for c in checks)

    n_pass = sum(1 for c in checks if c["status"] == "pass")
    n_warn = sum(1 for c in checks if c["status"] == "warn")
    n_fail = sum(1 for c in checks if c["status"] == "fail")

    has_hard_fail = any(c["status"] == "fail" and c["severity"] == "hard" for c in checks)
    overall = "hard_fail" if has_hard_fail else ("warnings" if (n_warn or n_fail) else "ok")

    return {
        "mode": "postmortem",
        "status": overall,
        "duration_seconds": round(time.monotonic() - t0, 3),
        "scouts": {
            "succeeded": scouts_ok,
            "total": scouts_total,
            "failed_scouts": [f["scout"] for f in failures],
        },
        "checks": checks,
        "failures": failures,
        "leaked_tokens_in_report": leaked,
        "summary": {
            "pass": n_pass,
            "warn": n_warn,
            "fail": n_fail,
            "total": len(checks),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="oss-veda guard — pre-flight and post-mortem health checks."
    )
    parser.add_argument(
        "--mode",
        choices=["preflight", "postmortem"],
        default="preflight",
        help="Check mode: 'preflight' (default) or 'postmortem'.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(tempfile.gettempdir()) / "oss-veda-raw.json",
        help="Path to raw.json for postmortem mode.",
    )
    args = parser.parse_args()

    if args.mode == "preflight":
        result = run_preflight()
    else:
        result = run_postmortem(args.input)

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")

    if result["status"] == "hard_fail":
        sys.exit(1)


if __name__ == "__main__":
    main()
