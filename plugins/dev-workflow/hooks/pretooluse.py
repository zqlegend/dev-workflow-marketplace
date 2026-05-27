#!/usr/bin/env python3
"""PreToolUse hook: security-sensitive-path edit reminder (advisory).

Fires on Edit/Write. If the edited file matches one of
`review.security_sensitive_paths` (from .claude/dev-workflow.local.md, read via
the shared read-config.py), surfaces a short generic reminder via the verified
advisory shape:

    {"hookSpecificOutput": {"permissionDecision": "allow"},
     "systemMessage": "security-sensitive path — ..."}

Otherwise emits a bare allow. Non-Edit/Write tools fast-exit (<5ms) with a bare
allow. Project-relative reads/globs resolve against the event `cwd`, not the
process working directory.

Uses the documented PreToolUse output shape (hookSpecificOutput.permissionDecision)
per the plugin-dev hook-development reference — NOT CYCAS's legacy
{"decision": "approve"} body (spec §7 hook-format correction).
"""

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

ALLOW = {"hookSpecificOutput": {"permissionDecision": "allow"}}
SECURITY_MESSAGE = (
    "security-sensitive path — review auth/crypto/input-validation invariants"
)


def _emit(obj):
    print(json.dumps(obj))


def _gmatch(path, glob):
    """Match `path` against `glob`; trailing /** means this dir + anything under."""
    if glob.endswith("/**"):
        base = glob[:-3]
        return path == base or path.startswith(base + "/")
    return fnmatch.fnmatch(path, glob)


def _security_paths(cwd):
    """Read review.security_sensitive_paths via read-config.py, resolved at `cwd`."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    rc = Path(plugin_root) / "scripts" / "read-config.py"
    if not rc.is_file():
        return []
    try:
        r = subprocess.run(
            ["python3", str(rc), "review.security_sensitive_paths"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if r.returncode != 0 or not r.stdout.strip():
        return []
    return [line for line in r.stdout.strip().splitlines() if line]


def main():
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        hook_input = {}

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        _emit(ALLOW)
        return

    tool_input = hook_input.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        _emit(ALLOW)
        return

    cwd = hook_input.get("cwd", "") or os.getcwd()

    # Normalize the edited path to a cwd-relative path so it matches
    # the project-relative globs in security_sensitive_paths.
    rel = file_path
    if os.path.isabs(file_path) and cwd:
        try:
            rel = os.path.relpath(file_path, cwd)
        except ValueError:
            rel = file_path

    globs = _security_paths(cwd)
    if any(_gmatch(rel, g) for g in globs):
        _emit({
            "hookSpecificOutput": {"permissionDecision": "allow"},
            "systemMessage": SECURITY_MESSAGE,
        })
        return

    _emit(ALLOW)


if __name__ == "__main__":
    main()
