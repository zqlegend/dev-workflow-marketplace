#!/usr/bin/env python3
"""Route a change (file list on stdin) to a reviewer role pair.

Output: two lines, `ROLE1=<role>` then `ROLE2=<role>` (abstract vocabulary).
Exit: 0 success; 2 empty input.
Flag: --no-cross-cut  skips the cross-cutting row (per-WU caller).
"""
import fnmatch, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RC = HERE / "read-config.py"

DEFAULT_TEST_GLOBS = ["tests/**", "**/*_test.*", "**/*.spec.*", "**/test_*"]

def cfg(key, default):
    r = subprocess.run(["python3", str(RC), key, default],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return default
    return r.stdout.rstrip("\n")

def cfg_list(key, default_list):
    r = subprocess.run(["python3", str(RC), key],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return default_list
    return [l for l in r.stdout.strip().splitlines() if l]

def gmatch(path, glob):
    # support a trailing /** as "this dir and anything under it"
    if glob.endswith("/**"):
        base = glob[:-3]
        return path == base or path.startswith(base + "/")
    return fnmatch.fnmatch(path, glob)

def main():
    args = sys.argv[1:]
    no_cross_cut = "--no-cross-cut" in args
    files = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    if not files:
        sys.stderr.write("route-change: empty input\n"); sys.exit(2)

    sec = cfg_list("review.security_sensitive_paths", [])
    tglobs = cfg_list("test_path_globs", DEFAULT_TEST_GLOBS)
    max_files = int(cfg("scope_thresholds.files", "5"))
    max_subs = int(cfg("scope_thresholds.subsystems", "1"))

    def is_test(f): return any(gmatch(f, g) for g in tglobs)
    def is_sec(f):  return any(gmatch(f, g) for g in sec)
    def is_type(f):
        low = f.lower()
        return (f.endswith(".d.ts") or f.endswith(".proto")
                or "types" in low or "interface" in low)

    top_dirs = {f.split("/")[0] for f in files if "/" in f}
    cross_cutting = (len(top_dirs) > max_subs) or (len(files) > max_files)

    # priority order
    if any(is_sec(f) for f in files):
        r1, r2 = "security-reviewer", "process-auditor"
    elif all(is_test(f) for f in files):
        r1, r2 = "test-reviewer", "process-auditor"
    elif all(is_type(f) for f in files):
        r1, r2 = "type-design-reviewer", "process-auditor"
    elif cross_cutting and not no_cross_cut:
        r1, r2 = "correctness-reviewer", "structural-architect"
    else:
        r1, r2 = "correctness-reviewer", "process-auditor"

    print(f"ROLE1={r1}")
    print(f"ROLE2={r2}")

if __name__ == "__main__":
    main()
