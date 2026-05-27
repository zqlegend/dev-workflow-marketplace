#!/usr/bin/env python3
"""Read a dotted key from .claude/dev-workflow.local.md YAML frontmatter.

Usage: read-config.py <dotted.key> [default]
  - prints the value (lists newline-joined; bools as true/false)
  - key absent + default given  -> print default, exit 0
  - key absent + no default     -> exit 3
  - config file absent + default-> print default, exit 0
  - config file absent + none   -> exit 3
  - PyYAML missing              -> exit 4 (actionable message)
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("dev-workflow: PyYAML required (pip install pyyaml)\n")
    sys.exit(4)

CONFIG = Path(".claude/dev-workflow.local.md")

def load_frontmatter(path):
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}

_MISSING = object()

def dig(data, dotted):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur

def emit(val):
    if isinstance(val, list):
        print("\n".join(str(x) for x in val))
    elif isinstance(val, bool):
        print("true" if val else "false")
    else:
        print(val)

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: read-config.py <dotted.key> [default]\n")
        sys.exit(2)
    key = sys.argv[1]
    default = sys.argv[2] if len(sys.argv) > 2 else None

    if not CONFIG.is_file():
        if default is not None:
            print(default); return
        sys.exit(3)

    val = dig(load_frontmatter(CONFIG), key)
    if val is _MISSING:
        if default is not None:
            print(default); return
        sys.exit(3)
    emit(val)

if __name__ == "__main__":
    main()
