#!/usr/bin/env python3
"""Deterministic APPROVE verifier for the CYCAS review-loop.

Exit codes:
  0 — all slices APPROVED, declared and embedded verdicts match
  1 — at least one non-APPROVE verdict
  2 — iteration file structurally invalid
  3 — declared vs embedded verdict drift

Usage: check-approve.py <iteration-file> <manifest-file>
"""
import json
import re
import sys
from pathlib import Path


VERDICT_RE = re.compile(r"^VERDICT:\s+(APPROVE|CONDITIONAL APPROVE|REJECT)\s*$", re.MULTILINE)
SLICE_HEADER_RE = re.compile(r"^## Slice:\s+(\S+)\s*$", re.MULTILINE)
REVIEWER_HEADER_RE = re.compile(r"^### Reviewer \d+ \([^)]+\)\s*$", re.MULTILINE)
NONCE_RE = re.compile(r"^nonce:\s+([0-9a-f]{8})\s*$", re.MULTILINE)
SLICES_EXPECTED_RE = re.compile(r"^slices_expected:\s+\[([^\]]*)\]\s*$", re.MULTILINE)


def die(code, msg):
    print(msg, file=sys.stderr)
    sys.exit(code)


def main():
    if len(sys.argv) != 3:
        die(2, "Usage: check-approve.py <iteration-file> <manifest-file>")

    iter_path = Path(sys.argv[1])
    manifest_path = Path(sys.argv[2])

    if not iter_path.exists():
        die(2, f"INVALID: iteration file not found: {iter_path}")
    if not manifest_path.exists():
        die(2, f"INVALID: manifest file not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    expected_slices = sorted(s["id"] for s in manifest["slices"])

    text = iter_path.read_text()

    nonce_match = NONCE_RE.search(text)
    if not nonce_match:
        die(2, "INVALID: missing or malformed 'nonce:' header (expected 8 hex chars)")
    nonce = nonce_match.group(1)

    expected_match = SLICES_EXPECTED_RE.search(text)
    if not expected_match:
        die(2, "INVALID: missing 'slices_expected:' header")
    declared_slices = sorted(s.strip() for s in expected_match.group(1).split(",") if s.strip())
    if declared_slices != expected_slices:
        die(2, f"INVALID: slices_expected={declared_slices} != manifest slices={expected_slices}")

    # Locate all BEGIN/END raw-response blocks scoped to the nonce.
    begin = f"<!-- BEGIN-RAW-{nonce} -->"
    end = f"<!-- END-RAW-{nonce} -->"
    begin_positions = [m.start() for m in re.finditer(re.escape(begin), text)]
    end_positions = [m.start() for m in re.finditer(re.escape(end), text)]
    if len(begin_positions) != len(end_positions):
        die(2, f"INVALID: {len(begin_positions)} BEGIN-RAW markers but {len(end_positions)} END-RAW markers")

    # Pair them in order; require non-interleaving.
    pairs = []
    for b, e in zip(begin_positions, end_positions):
        if e <= b:
            die(2, "INVALID: END-RAW appears at or before its paired BEGIN-RAW")
        pairs.append((b, e))

    # Check non-interleaving: each BEGIN i must be after END of pair i-1.
    for i in range(1, len(pairs)):
        prev_end = pairs[i - 1][1]
        this_begin = pairs[i][0]
        if this_begin < prev_end:
            die(2, "INVALID: raw-response blocks interleave")

    # Mask the raw-response byte ranges out of the document.
    masked = list(text)
    for b, e in pairs:
        for i in range(b, e + len(end)):
            if i < len(masked):
                masked[i] = " "
    masked_text = "".join(masked)

    # Walk slices.
    slice_offsets = [(m.start(), m.group(1)) for m in SLICE_HEADER_RE.finditer(masked_text)]
    if len(slice_offsets) != len(expected_slices):
        die(2, f"INVALID: expected {len(expected_slices)} slice sections, found {len(slice_offsets)}")

    slice_offsets.append((len(masked_text), None))

    approvals = 0
    for i, (start, slice_id) in enumerate(slice_offsets[:-1]):
        end_of_slice = slice_offsets[i + 1][0]
        section = masked_text[start:end_of_slice]

        reviewer_positions = [m.start() for m in REVIEWER_HEADER_RE.finditer(section)]
        if len(reviewer_positions) != 2:
            die(2, f"INVALID: slice '{slice_id}' has {len(reviewer_positions)} Reviewer subsections, expected 2")

        reviewer_positions.append(len(section))
        for j in range(2):
            sub = section[reviewer_positions[j]:reviewer_positions[j + 1]]
            declared = VERDICT_RE.search(sub)
            if not declared:
                die(2, f"INVALID: slice '{slice_id}' reviewer {j+1} has no declared VERDICT line")
            declared_verdict = declared.group(1)

            # Find the corresponding raw-response block: locate by document-order
            # in the *unmasked* text, matching the reviewer subsection's absolute range.
            abs_sub_start = start + reviewer_positions[j]
            abs_sub_end = start + reviewer_positions[j + 1]
            # Pick the first raw block fully inside this reviewer subsection.
            matching_pair = None
            for b, e in pairs:
                if abs_sub_start <= b and e < abs_sub_end:
                    matching_pair = (b, e)
                    break
            if matching_pair is None:
                die(2, f"INVALID: slice '{slice_id}' reviewer {j+1} has no embedded raw-response block")

            raw_content = text[matching_pair[0] + len(begin):matching_pair[1]]
            embedded = VERDICT_RE.search(raw_content)
            if not embedded:
                die(2, f"INVALID: slice '{slice_id}' reviewer {j+1} raw block has no VERDICT line")
            embedded_verdict = embedded.group(1)

            if declared_verdict != embedded_verdict:
                die(3, f"DRIFT: slice '{slice_id}' reviewer {j+1}: declared={declared_verdict} embedded={embedded_verdict}")

            if declared_verdict != "APPROVE":
                die(1, f"NOT-APPROVED: slice '{slice_id}' reviewer {j+1} verdict={declared_verdict}")

            approvals += 1

    print(f"OK: all {len(expected_slices)} slices APPROVED (verdict match verified, nonce={nonce})")
    sys.exit(0)


if __name__ == "__main__":
    main()
