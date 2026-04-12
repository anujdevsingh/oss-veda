# Changelog

All notable changes to oss-veda are documented in this file.

## [1.2.0] - 2026-04-12

### Added
- **veda-guard agent**: automatic pre-flight, security, and post-mortem checks
  - 7 pre-flight checks: uv installed, Python version, temp dir writable, network reachable, GITHUB_TOKEN, scripts exist, config valid
  - 4 security checks: cache size limit, unexpected file detection, SHA256 script checksums, history file integrity
  - 3 post-mortem checks: scout success rate, report file validation, token leak detection
- `checksums.json` for script tamper detection
- `--skip-guard` flag for `/veda` and `/veda-deep`
- Dev helper `_dev_update_checksums.py` for release maintenance

### Changed
- GITHUB_TOKEN check moved from standalone Step 0 into guard pre-flight (check #5)
- Pipeline now has 6 steps: guard → scouts → rank → report → strategy → post-mortem

## [1.1.1] - 2026-04-10

### Fixed
- HuggingFace URLs now correctly link to `huggingface.co/{id}`
- JSON decode error handling in HuggingFace and Reddit scouts
- `Retry-After` header parsing handles HTTP-date format
- Path traversal protection on cache file paths
- Defensive `.get()` access throughout report generator
- Missing `objectID` guard in Hacker News results
- Removed unused `httpx`/`pydantic` dependencies from scoring script
- Missing `encoding="utf-8"` on cache file reads
- `/veda-deep` command defaults topic to "ai" when no argument given

### Changed
- Plugin manifest version synced to 1.1.1
- Agent files updated with proper frontmatter (`model`, `maxTurns`)
- SKILL.md no longer uses hardcoded `/tmp` paths
- Scoring reference docs updated to match v1.1.0 algorithm
- README GITHUB_TOKEN changed from "required" to "recommended"

## [1.1.0] - 2026-04-10

### Added
- Centralized `config.json` for all settings
- Exponential backoff with retry on GitHub 403/429
- Per-scout 3-minute timeout via `asyncio.wait_for()`
- Run history tracking (TSV log in cache directory)
- HuggingFace likes/downloads included in social signals
- Structural complexity analysis (steps to reproduce, checkboxes, acceptance criteria)

### Changed
- Logarithmic star scoring (small fast-growing repos compete with giants)
- Exponential freshness decay with configurable half-life
- Engagement sweet-spot detection (1-3 comments = ideal)
- Soft language scoring (no more hard-filtering unfamiliar languages)
- Windows compatibility (no hardcoded `/tmp` paths)

### Fixed
- `datetime.utcnow()` deprecation warnings
- Unicode/encoding errors on Windows
- Report shows next scan date as tomorrow, not today

## [1.0.0] - 2026-04-10

### Added
- Initial release
- 5 parallel scouts (GitHub, HN, Reddit, HuggingFace, Papers with Code)
- Career impact scoring algorithm (repo momentum + issue quality + skill fit)
- 3 skills: oss-veda, veda-rank, veda-write
- 5 subagents: github-scout, hn-scout, reddit-scout, hf-scout, pwc-scout
- 2 commands: /veda, /veda-deep
- PEP 723 uv single-file scripts with inline metadata
