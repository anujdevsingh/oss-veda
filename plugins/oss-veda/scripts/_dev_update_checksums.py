#!/usr/bin/env python3
"""Dev-only: regenerate checksums.json from current script files."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
CHECKSUMS_FILE = PLUGIN_ROOT / "checksums.json"

# Read version from plugin.json
plugin_json = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
version = plugin_json["version"]

# Hash all .py files in scripts/ (excluding this file and __pycache__)
files = {}
for py_file in sorted(SCRIPTS_DIR.glob("*.py")):
    if py_file.name.startswith("_"):
        continue
    # Normalize line endings (CRLF → LF) before hashing for cross-platform consistency
    content = py_file.read_bytes().replace(b"\r\n", b"\n")
    sha256 = hashlib.sha256(content).hexdigest()
    files[f"scripts/{py_file.name}"] = sha256

checksums = {
    "version": version,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "algorithm": "sha256",
    "files": files,
}

CHECKSUMS_FILE.write_text(json.dumps(checksums, indent=2) + "\n")
print(f"Wrote {len(files)} checksums to {CHECKSUMS_FILE}")
for path, sha in files.items():
    print(f"  {sha[:12]}...  {path}")
