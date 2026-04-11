# veda-guard agent — Design Spec

**Status**: Draft — awaiting user approval
**Date**: 2026-04-11
**Author**: Claude (with Anuj)
**Target version**: oss-veda v1.2.0

---

## 1. Goal

Add a **guard agent** that runs automatically as Step 0 of the oss-veda pipeline. It performs pre-flight environment checks, security/integrity audits, and post-mortem diagnosis of failures. It blocks the pipeline only on hard failures (things that would cause the pipeline to fail anyway), warns on soft issues, and stays silent when everything is healthy.

The guard never auto-edits user files or scripts. It either fixes safe environmental things (e.g. creates a missing temp directory) or tells the user how to fix the rest in plain English.

## 2. Non-goals

- **Not a live watchdog** — the Python orchestrator already handles per-scout timeouts, retries, and graceful degradation. The guard does NOT supervise the pipeline while it runs.
- **Not an auto-fixer for Python scripts** — if a scout breaks because of an API change or a code bug, the guard diagnoses and reports it. It never edits `.py` files.
- **Not a system installer** — does not install `uv`, Python, or any dependencies. Tells the user how to install them.
- **Not a shell-config modifier** — does not write to `.bashrc`, `.zshrc`, environment variables, etc.

## 3. User-visible behavior

### 3.1 The happy path (everything healthy, has token)

User runs `/veda`. Within ~3 seconds, they see:

```
✅ Guard: all checks passed (uv 0.4.20, Python 3.12, network OK, scripts verified)
Launching 5 parallel scouts...
```

Then the normal pipeline continues. Total guard overhead: ~3 seconds.

### 3.2 Soft warnings (continue, but inform)

User runs `/veda` without GITHUB_TOKEN. They see:

```
✅ Guard: pre-flight passed
🟡 Guard warnings:
  - GITHUB_TOKEN not set (rate-limited to 10/min instead of 30/min)
  - Last run had 1/5 scouts fail (papers_with_code timed out)
  - Cache size: 47 MB (healthy, <100 MB threshold)
Launching 5 parallel scouts...
```

Pipeline continues normally.

### 3.3 Hard failure (block, fix instructions)

User runs `/veda` without `uv` installed. They see:

```
🔴 Guard: hard failure — cannot run pipeline

Problem: `uv` is not installed or not on PATH.
The plugin uses uv to run Python scripts with auto-installed dependencies.

Fix it:
  macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh
  Windows:      powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  Or visit:     https://docs.astral.sh/uv/getting-started/installation/

After installing, restart Claude Code and re-run /veda.
```

Pipeline does NOT run. User fixes the issue, retries.

### 3.4 Post-mortem diagnosis (after pipeline runs with errors)

If 2 scouts failed, after the report is generated the user sees an additional section appended:

```
🟡 Post-mortem (from veda-guard):
  - papers_with_code: timed out after 180s (the PwC API has been flaky lately —
    this is a known issue, not a bug in the plugin)
  - reddit: HTTP 429 rate-limited (wait 5 minutes before re-running, or use
    /veda --no-cache to skip cached results next time)

Pipeline succeeded with 3/5 scouts. Report still useful.
```

## 4. Architecture

### 4.1 Where the guard lives

The guard is implemented as **two pieces**:

1. **`scripts/guard.py`** — A new PEP 723 single-file Python script that runs the deterministic checks (filesystem, subprocess, network HEAD, checksums, JSON parsing). This is the workhorse — it does all the heavy lifting in one fast process.
2. **`agents/veda-guard.md`** — A native Claude subagent that orchestrates `guard.py`, reads its JSON output, and presents the results to the user in plain English. This adds the "explain in human terms" layer that pure Python can't do well.

### 4.2 Why two pieces and not one?

- **Speed**: Python checks (file existence, subprocess calls, network HEAD) are 10-100x faster and cheaper than asking an LLM to do them via Bash one at a time.
- **Determinism**: Checksum verification, JSON parsing, file existence are facts, not judgments. No LLM needed.
- **LLM value-add**: The LLM is only useful for the "translate this error to plain English and suggest a fix" step — the post-mortem diagnosis. That's a small final step, not the whole agent.

This matches the existing plugin pattern: deterministic Python scripts in `scripts/`, thin orchestrator agents in `agents/`.

### 4.3 How the guard plugs into the pipeline

Modify [SKILL.md](plugins/oss-veda/skills/oss-veda/SKILL.md) and [veda-deep.md](plugins/oss-veda/commands/veda-deep.md) so that **Step 0** invokes the guard before the existing GITHUB_TOKEN check:

```
Step 0a: Run guard pre-flight + security checks via guard.py
Step 0b: If guard returns hard fail → stop, show fix instructions, exit
Step 0c: If guard returns soft warnings → show them, continue
Step 0d: If guard returns OK → silent pass
Step 0e: Existing GITHUB_TOKEN check (now subsumed into guard, can be removed)
Step 1: Run scouts (existing)
Step 2: Rank (existing)
Step 3: Report (existing)
Step 4: Run guard post-mortem on the raw.json results, append diagnosis to report
```

The existing standalone GITHUB_TOKEN check in SKILL.md becomes redundant — it's now part of the guard's pre-flight checks (item #5 in the list below).

## 5. Component details

### 5.1 `scripts/guard.py`

PEP 723 single-file Python script. Zero external dependencies (uses only stdlib). Two modes:

#### Mode A: pre-flight check (default)
```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/guard.py --mode preflight
```

Runs all 11 pre-flight + security checks in sequence (~3 seconds total). Outputs JSON to stdout:

```json
{
  "mode": "preflight",
  "status": "ok" | "warnings" | "hard_fail",
  "duration_seconds": 2.4,
  "checks": [
    {
      "id": "uv_installed",
      "name": "uv installed",
      "status": "pass" | "warn" | "fail",
      "severity": "hard" | "soft",
      "details": "uv 0.4.20 found at /usr/local/bin/uv",
      "fix_hint": null
    },
    {
      "id": "github_token",
      "name": "GITHUB_TOKEN set",
      "status": "warn",
      "severity": "soft",
      "details": "Not set in environment",
      "fix_hint": "See README §'Setting GITHUB_TOKEN' for setup instructions. Pipeline will run rate-limited."
    },
    ...
  ],
  "summary": {
    "passed": 9,
    "warned": 2,
    "failed": 0,
    "total": 11
  }
}
```

#### Mode B: post-mortem diagnosis
```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/guard.py --mode postmortem --input <raw.json>
```

Reads the pipeline's `oss-veda-raw.json`, identifies which scouts failed and why, classifies each failure (rate limit, network, timeout, API change, other), and outputs a JSON report:

```json
{
  "mode": "postmortem",
  "scouts_succeeded": 3,
  "scouts_total": 5,
  "failures": [
    {
      "scout": "papers_with_code",
      "category": "timeout",  // one of: timeout | rate_limit | network | bad_response | api_change | unknown
      "raw_error": "TimeoutError after 180s",
      "diagnosis": "PwC API was unresponsive. Often flaky, retry later.",
      "user_action": "No action needed — pipeline succeeded with 4/5 sources"
    }
  ],
  "leaked_tokens_in_report": false
}
```

### 5.2 `agents/veda-guard.md`

Native Claude subagent. Frontmatter:

```yaml
---
name: veda-guard
description: >
  Guards the oss-veda pipeline. Runs pre-flight checks, security audits,
  and post-mortem diagnosis. Invoked automatically by the main oss-veda
  skill before and after the pipeline runs.
model: haiku
maxTurns: 5
tools: Bash, Read
---
```

(Using **haiku** because the guard's job is mechanical — run script, parse JSON, format output. Sonnet would be wasteful.)

The agent body has explicit execution instructions (same pattern we just fixed for the scout agents):
- Step 1: Execute `guard.py --mode preflight` via Bash
- Step 2: Parse JSON output
- Step 3: If `status == "hard_fail"`, format the failures into the user-facing block from §3.3 and STOP. Return a structured JSON message back to the calling skill so it knows to abort.
- Step 4: If `status == "warnings"`, format the §3.2 message and return `continue: true`.
- Step 5: If `status == "ok"`, return the §3.1 one-line success message and `continue: true`.

For post-mortem mode (called after the pipeline finishes):
- Step 1: Execute `guard.py --mode postmortem --input <raw.json>` via Bash
- Step 2: Parse JSON, format the §3.4 diagnosis block
- Step 3: Append to the report

### 5.3 `checksums.json` (new file at plugin root)

A new file shipped with the plugin: `plugins/oss-veda/checksums.json`

```json
{
  "version": "1.2.0",
  "generated_at": "2026-04-11T00:00:00Z",
  "algorithm": "sha256",
  "files": {
    "scripts/run_scouts.py": "abc123...",
    "scripts/github_scout.py": "def456...",
    "scripts/hn_scout.py": "...",
    "scripts/reddit_scout.py": "...",
    "scripts/hf_scout.py": "...",
    "scripts/pwc_scout.py": "...",
    "scripts/rank_opportunities.py": "...",
    "scripts/generate_report.py": "...",
    "scripts/guard.py": "..."
  }
}
```

Maintenance: a helper script `scripts/_dev_update_checksums.py` (not shipped to users — dev-only) regenerates this file. The release process will be:

1. Make code changes
2. Run `python scripts/_dev_update_checksums.py` to regenerate `checksums.json`
3. Bump version in `plugin.json`
4. Commit and tag

If the user manually edits a script (e.g. for debugging), the checksum mismatch becomes a 🔴 hard fail with the message:

```
🔴 Script integrity check failed: scripts/github_scout.py has been modified.

Expected SHA256: abc123...
Actual SHA256:   xyz789...

This could mean:
  (a) You modified the file yourself for debugging — that's fine, but the
      guard will block until you reinstall the plugin or revert your changes.
  (b) Something else modified the file, which is concerning.

Fix: /plugin update oss-veda  (this will restore the original files)
```

(This addresses your concern about "something breaks the user's local system" — if anything weird touches the plugin files, the guard catches it.)

## 6. The 14 checks (full list)

### Pre-flight (7 checks)

| # | Check | Implementation | Severity | Auto-fix? |
|---|---|---|---|---|
| 1 | `uv` installed | `subprocess.run(["uv", "--version"])` | 🔴 Hard | No, show install link |
| 2 | Python ≥ 3.11 | `sys.version_info` | 🔴 Hard | No, show install link |
| 3 | Temp dir writable | Try writing a 1-byte test file to `tempfile.gettempdir()/oss-veda-cache/` | 🔴 Hard | Yes — create dir if missing |
| 4 | Network reachable | `socket.create_connection(("api.github.com", 443), timeout=5)` | 🔴 Hard | No, show diagnosis |
| 5 | GITHUB_TOKEN set | `os.environ.get("GITHUB_TOKEN")` | 🟡 Soft | No, show README link |
| 6 | Plugin scripts exist | Glob `${CLAUDE_PLUGIN_ROOT}/scripts/*.py`, expect 9 files | 🔴 Hard | No, show reinstall link |
| 7 | config.json valid | `json.load()` then check required keys | 🟡 Soft | Yes — fall back to defaults |

### Security (4 checks)

| # | Check | Implementation | Severity | Auto-fix? |
|---|---|---|---|---|
| 8 | Cache dir size sane | `sum(f.stat().st_size for f in cache_dir.glob("**/*"))`, < 100 MB | 🟡 Soft | Yes — auto-cleanup if >100 MB |
| 9 | No files outside expected paths | Glob cache dir, confirm only known filenames present | 🟡 Soft | No, just warn |
| 10 | Script checksums match | SHA256 of each `scripts/*.py` vs `checksums.json` | 🔴 Hard | No, show reinstall link |
| 11 | run_history.tsv sane | First line is the expected header, no row >10KB | 🟡 Soft | Yes — truncate if corrupted |

### Post-mortem (3 checks)

| # | Check | Implementation | Severity | Auto-fix? |
|---|---|---|---|---|
| 12 | Scouts succeeded | Read `_metadata.scouts_succeeded` from raw.json | 🟡 if 3-4/5, 🔴 if 0-2/5 | No |
| 13 | Report file exists | Check `tempfile.gettempdir()/oss-veda-report.md` exists, >100 bytes | 🔴 Hard | No |
| 14 | No tokens in report | Grep for `ghp_`, `github_pat_`, `Bearer ` in report content | 🔴 Hard | No (but should never happen — defense in depth) |

## 7. Failure mode catalog (for post-mortem diagnosis)

The post-mortem phase classifies failures into categories so it can give meaningful diagnosis. Each scout's exception message gets matched against patterns:

| Pattern in error | Category | Diagnosis | User action |
|---|---|---|---|
| `TimeoutError`, `asyncio.TimeoutError` | `timeout` | Scout exceeded 3-min budget. API likely slow or hung. | None — try again later |
| `403`, `429`, `rate limit` | `rate_limit` | Hit API rate limit. Backoff did not recover in time. | Wait 5 min OR set `GITHUB_TOKEN` for higher limits |
| `ConnectionError`, `getaddrinfo failed`, `Network unreachable` | `network` | Cannot reach API host. Check internet. | Check network |
| `JSONDecodeError`, `Expecting value` | `bad_response` | API returned non-JSON (HTML error page, maintenance) | None — usually transient |
| `KeyError`, `AttributeError` in scout code | `api_change` | API response shape changed. Likely a plugin bug. | Report issue at github.com/anujdevsingh/oss-veda/issues |
| Anything else | `unknown` | Unrecognized error pattern. | Report issue with full error |

The guard is **conservative**: when in doubt, it categorizes as `unknown` and reports the raw error rather than guessing.

## 8. Failure modes of the guard itself

What if the guard breaks?

| Failure | Effect | Mitigation |
|---|---|---|
| `guard.py` crashes (unhandled exception) | Pipeline must not be blocked by a buggy guard | The skill catches non-zero exit from guard.py and falls back to "guard unavailable, running pipeline anyway" — pipeline still runs |
| `guard.py` outputs malformed JSON | Same as above | JSON parse failure in skill → fallback to "guard unavailable" |
| Network HEAD to api.github.com fails but actual scout calls would work | False positive hard-fail | Use 5-second timeout, allow user to override with `--skip-guard` flag (escape hatch) |
| Checksums file is missing or corrupted | Can't verify scripts | Soft warn, not hard fail — guard shouldn't be brittle |
| User wants to disable the guard entirely | Pipeline should still work | New flag: `/veda --skip-guard` and `/veda-deep --skip-guard` |

The principle: **the guard must never be the reason a working pipeline fails.** If the guard itself is broken, it gets out of the way.

## 9. Files added / modified

### New files
- `plugins/oss-veda/scripts/guard.py` (~400 lines, PEP 723, stdlib only)
- `plugins/oss-veda/scripts/_dev_update_checksums.py` (~50 lines, dev-only helper)
- `plugins/oss-veda/agents/veda-guard.md` (~80 lines)
- `plugins/oss-veda/checksums.json` (generated)

### Modified files
- `plugins/oss-veda/skills/oss-veda/SKILL.md` — add Step 0 (guard pre-flight) and Step 4 (guard post-mortem); remove the existing GITHUB_TOKEN-only check (now part of guard)
- `plugins/oss-veda/commands/veda-deep.md` — same Step 0 + Step 4 additions
- `plugins/oss-veda/commands/veda.md` — add `--skip-guard` flag pass-through
- `plugins/oss-veda/CHANGELOG.md` — v1.2.0 entry
- `plugins/oss-veda/.claude-plugin/plugin.json` — bump to 1.2.0
- `README.md` — new section: "How the guard works", note the `--skip-guard` flag

### Unchanged
- All 5 scout scripts
- `rank_opportunities.py`, `generate_report.py`, `run_scouts.py`
- All 5 scout agent .md files
- The 3 skill .md files (other than the orchestrator SKILL.md)

## 10. Testing strategy

Manual test matrix (no automated CI yet, since this is a Claude Code plugin):

| Scenario | Expected guard behavior |
|---|---|
| Fresh install, everything healthy | Silent pass, ~3s overhead, pipeline runs normally |
| `uv` not installed | Hard fail with install link, pipeline does NOT run |
| No GITHUB_TOKEN | Soft warning, pipeline runs |
| Network unplugged | Hard fail "no network", pipeline does NOT run |
| One scout returns empty | Soft warning in post-mortem, pipeline runs |
| GitHub returns 429 mid-run | Post-mortem categorizes as rate_limit, suggests wait |
| `github_scout.py` manually edited | Hard fail "checksum mismatch", pipeline does NOT run |
| Cache dir is 200 MB | Soft warning, auto-cleans down to <100 MB |
| `guard.py` itself has a bug (simulated by `raise Exception` at top) | Skill detects non-zero exit, prints "guard unavailable", runs pipeline anyway |
| User runs `/veda --skip-guard` | Skip guard entirely, run pipeline directly |

## 11. What this changes about plugin maintenance

**One new responsibility for the maintainer (you)**: every time a `.py` file changes in `scripts/`, you must regenerate `checksums.json` before tagging a release. The dev helper `_dev_update_checksums.py` makes this a one-command operation:

```bash
python plugins/oss-veda/scripts/_dev_update_checksums.py
```

This can be added to a pre-commit hook or release script later if it becomes annoying.

## 12. Open questions / risks

1. **Checksum maintenance burden**: If you forget to regenerate `checksums.json`, every user gets a hard fail on their next run. Mitigation: add a CI check (later) that fails the build if `checksums.json` doesn't match the actual files.

2. **Network HEAD false positives**: Some users on corporate networks may have api.github.com blocked but the actual scouts might work via a proxy. Mitigation: the `--skip-guard` flag is the escape hatch.

3. **Haiku model availability**: The agent uses haiku 4.5. If the user is on a plan where haiku isn't available, this could fail. Mitigation: agent frontmatter says `model: haiku` but Claude Code falls back gracefully if unavailable.

4. **Should the guard run on every invocation or cache its result?** Current design: runs on every `/veda`. ~3 seconds overhead. If that's too much, we can cache the pre-flight result for 1 hour in temp dir. **This is a YAGNI question — let's not add caching until it's actually annoying.**

## 13. Version bump

This is a **minor version bump**: v1.1.1 → v1.2.0.

Justification: adds a new agent, new script, new file (`checksums.json`), and a new user-facing behavior (the guard messages). No breaking changes to existing commands or configuration.

---

**End of design spec.**
