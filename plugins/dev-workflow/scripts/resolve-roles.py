#!/usr/bin/env python3
"""Rewrite a manifest's abstract roles into concrete subagent_type strings.

Usage: resolve-roles.py <manifest.json>
Static, idempotent: only roles still in the abstract vocabulary are rewritten.
External agents used only if pr-review-toolkit is installed AND
review.use_external_agents is true; otherwise plugin-owned fallbacks.
"""
import json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RC = HERE / "read-config.py"

OWNED = {"process-auditor", "structural-architect",
         "correctness-reviewer", "security-reviewer",
         "test-reviewer", "type-design-reviewer"}

EXTERNAL = {
    "correctness-reviewer": "pr-review-toolkit:code-reviewer",
    "security-reviewer":   "pr-review-toolkit:silent-failure-hunter",
    "test-reviewer":       "pr-review-toolkit:pr-test-analyzer",
    "type-design-reviewer":"pr-review-toolkit:type-design-analyzer",
}
ALWAYS_OWNED = {"process-auditor", "structural-architect"}

def use_external():
    r = subprocess.run(["python3", str(RC), "review.use_external_agents", "false"],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"

def pr_toolkit_installed():
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return False
    # plugins-root = parent of cache_root = 4 dirname hops from CLAUDE_PLUGIN_ROOT
    plugins_root = Path(root).parents[3]   # .../.claude/plugins
    reg = plugins_root / "installed_plugins.json"
    if not reg.is_file():
        return False
    try:
        data = json.loads(reg.read_text())
    except Exception:
        return False
    # real registry shape: {"version": N, "plugins": {"pr-review-toolkit@<mkt>": [...]}}
    plugins = data.get("plugins", data) if isinstance(data, dict) else {}
    return any(k.split("@")[0] == "pr-review-toolkit" for k in plugins)

def resolve(role, external_ok):
    if role in ALWAYS_OWNED:
        return f"dev-workflow:{role}"
    if role in OWNED:
        if external_ok and role in EXTERNAL:
            return EXTERNAL[role]
        return f"dev-workflow:{role}"
    return role   # already concrete -> idempotent no-op

def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: resolve-roles.py <manifest.json>\n"); sys.exit(2)
    path = Path(sys.argv[1])
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"resolve-roles: cannot read manifest {path}: {e}\n")
        sys.exit(2)
    external_ok = use_external() and pr_toolkit_installed()
    for sl in manifest.get("slices", []):
        sl["roles"] = [resolve(r, external_ok) for r in sl.get("roles", [])]
    path.write_text(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
