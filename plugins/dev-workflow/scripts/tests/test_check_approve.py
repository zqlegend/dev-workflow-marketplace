"""Tests for check-approve.py — the deterministic APPROVE verifier."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-approve.py"
FIXTURES = Path(__file__).parent / "fixtures"


def run(iter_file, manifest_file):
    """Invoke check-approve.py; return (exit_code, stdout+stderr)."""
    result = subprocess.run(
        ["python3", str(SCRIPT), str(iter_file), str(manifest_file)],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def test_ok_all_approve(tmp_path):
    code, out = run(FIXTURES / "iter_ok.md", FIXTURES / "manifest_simple.json")
    assert code == 0, f"Expected exit 0, got {code}. Output:\n{out}"
    assert "OK:" in out


def _write(tmp, contents, name="iter.md"):
    p = tmp / name
    p.write_text(contents)
    return p


def test_exit1_non_approve(tmp_path):
    iter_file = _write(tmp_path, """nonce: a7f3c2e9
slices_expected: [default]

## Slice: default

### Reviewer 1 (physics-general)
VERDICT: REJECT
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: REJECT
<!-- END-RAW-a7f3c2e9 -->

### Reviewer 2 (process-auditor)
VERDICT: APPROVE
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: APPROVE
<!-- END-RAW-a7f3c2e9 -->
""")
    code, out = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 1, f"Expected exit 1, got {code}. Output:\n{out}"


def test_exit2_missing_nonce(tmp_path):
    iter_file = _write(tmp_path, """slices_expected: [default]

## Slice: default

### Reviewer 1 (physics-general)
VERDICT: APPROVE
""")
    code, _ = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 2


def test_exit2_bad_nonce_format(tmp_path):
    iter_file = _write(tmp_path, """nonce: xyz
slices_expected: [default]
""")
    code, _ = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 2


def test_exit2_missing_slices_expected(tmp_path):
    iter_file = _write(tmp_path, """nonce: a7f3c2e9
""")
    code, _ = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 2


def test_exit2_slices_mismatch(tmp_path):
    iter_file = _write(tmp_path, """nonce: a7f3c2e9
slices_expected: [wrong_id]
""")
    code, _ = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 2


def test_exit2_unbalanced_delimiters(tmp_path):
    iter_file = _write(tmp_path, """nonce: a7f3c2e9
slices_expected: [default]

## Slice: default

### Reviewer 1 (physics-general)
VERDICT: APPROVE
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: APPROVE
<!-- END-RAW-a7f3c2e9 -->

### Reviewer 2 (process-auditor)
VERDICT: APPROVE
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: APPROVE
""")
    code, _ = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 2


def test_exit2_nonce_delimiter_mismatch(tmp_path):
    iter_file = _write(tmp_path, """nonce: a7f3c2e9
slices_expected: [default]

## Slice: default

### Reviewer 1 (physics-general)
VERDICT: APPROVE
<!-- BEGIN-RAW-deadbeef -->
VERDICT: APPROVE
<!-- END-RAW-deadbeef -->

### Reviewer 2 (process-auditor)
VERDICT: APPROVE
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: APPROVE
<!-- END-RAW-a7f3c2e9 -->
""")
    code, _ = run(iter_file, FIXTURES / "manifest_simple.json")
    # Only one of the two required blocks exists under the declared nonce.
    # Either exit 2 (structural — missing reviewer block) or exit 2 (count mismatch).
    assert code == 2


def test_exit3_drift(tmp_path):
    iter_file = _write(tmp_path, """nonce: a7f3c2e9
slices_expected: [default]

## Slice: default

### Reviewer 1 (physics-general)
VERDICT: APPROVE
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: REJECT
<!-- END-RAW-a7f3c2e9 -->

### Reviewer 2 (process-auditor)
VERDICT: APPROVE
<!-- BEGIN-RAW-a7f3c2e9 -->
VERDICT: APPROVE
<!-- END-RAW-a7f3c2e9 -->
""")
    code, out = run(iter_file, FIXTURES / "manifest_simple.json")
    assert code == 3, f"Expected exit 3 (drift), got {code}. Output:\n{out}"
