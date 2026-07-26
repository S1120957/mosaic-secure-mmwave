from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SESSION = Path("data/measured/challenge-feasibility/session02")
TARGET = SESSION / "profile_switch_target_full.bin"
BACKGROUND = SESSION / "profile_switch_bg_full.bin"
TIMESTAMPS = SESSION / "per_subframe_timestamps.json"
OUTPUT = SESSION / "validation_report.json"

EXPECTED_SUBFRAMES = 2000
EXPECTED_BYTES_PER_SUBFRAME = 65536
EXPECTED_BINARY_SIZE = EXPECTED_SUBFRAMES * EXPECTED_BYTES_PER_SUBFRAME


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return None


for required in (TARGET, BACKGROUND, TIMESTAMPS):
    if not required.exists():
        raise SystemExit(f"Missing required file: {required}")

rows = json.loads(TIMESTAMPS.read_text(encoding="utf-8-sig"))
if not isinstance(rows, list):
    raise SystemExit("Timestamp JSON must contain a list.")

profile_sequence_valid = all(
    row.get("profile_id") == ("P0" if index % 2 == 0 else "P1")
    for index, row in enumerate(rows)
)
subframe_indices_valid = all(
    row.get("subframe_index") == index
    for index, row in enumerate(rows)
)
advanced_frame_indices_valid = all(
    row.get("advanced_frame_index") == index // 2
    for index, row in enumerate(rows)
)
byte_accounting_valid = all(
    row.get("bytes_received") == (index + 1) * EXPECTED_BYTES_PER_SUBFRAME
    for index, row in enumerate(rows)
)

timestamp_values = [
    row.get("timestamp_ns")
    for row in rows
    if isinstance(row.get("timestamp_ns"), int)
]
timestamps_monotonic = (
    len(timestamp_values) == len(rows)
    and all(
        timestamp_values[index] > timestamp_values[index - 1]
        for index in range(1, len(timestamp_values))
    )
)
intervals_ns = [
    timestamp_values[index] - timestamp_values[index - 1]
    for index in range(1, len(timestamp_values))
]

structural_checks = {
    "target_size_valid": TARGET.stat().st_size == EXPECTED_BINARY_SIZE,
    "background_size_valid": BACKGROUND.stat().st_size == EXPECTED_BINARY_SIZE,
    "record_count_valid": len(rows) == EXPECTED_SUBFRAMES,
    "profile_sequence_valid": profile_sequence_valid,
    "subframe_indices_valid": subframe_indices_valid,
    "advanced_frame_indices_valid": advanced_frame_indices_valid,
    "byte_accounting_valid": byte_accounting_valid,
    "timestamps_present": len(timestamp_values) == len(rows),
    "timestamps_monotonic": timestamps_monotonic,
}

report = {
    "report_type": "machine_derived_structural_validation",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "session_id": "session02",
    "git_commit": git_commit(),
    "publication_eligibility": False,
    "publication_eligibility_reason": (
        "Ground-truth, runtime-control, and acquisition-provenance "
        "metadata remain incomplete."
    ),
    "files": {
        "target": {
            "path": TARGET.as_posix(),
            "size_bytes": TARGET.stat().st_size,
            "expected_size_bytes": EXPECTED_BINARY_SIZE,
            "sha256": sha256(TARGET),
        },
        "background": {
            "path": BACKGROUND.as_posix(),
            "size_bytes": BACKGROUND.stat().st_size,
            "expected_size_bytes": EXPECTED_BINARY_SIZE,
            "sha256": sha256(BACKGROUND),
        },
        "timestamps": {
            "path": TIMESTAMPS.as_posix(),
            "records": len(rows),
            "expected_records": EXPECTED_SUBFRAMES,
        },
    },
    "structural_checks": structural_checks,
    "timestamp_statistics": {
        "first_timestamp_ns": timestamp_values[0] if timestamp_values else None,
        "last_timestamp_ns": timestamp_values[-1] if timestamp_values else None,
        "capture_span_seconds": (
            (timestamp_values[-1] - timestamp_values[0]) / 1e9
            if len(timestamp_values) >= 2
            else None
        ),
        "mean_interval_ms": (
            sum(intervals_ns) / len(intervals_ns) / 1e6
            if intervals_ns else None
        ),
        "minimum_interval_ms": min(intervals_ns) / 1e6 if intervals_ns else None,
        "maximum_interval_ms": max(intervals_ns) / 1e6 if intervals_ns else None,
    },
    "validation_status": {
        "structural_validation": (
            "PASS" if all(structural_checks.values()) else "FAIL"
        ),
        "ground_truth_review": "PENDING",
        "runtime_control_review": "PENDING",
        "acquisition_provenance_review": "PENDING",
    },
}

OUTPUT.write_text(
    json.dumps(report, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, indent=2))
print(f"\nWritten: {OUTPUT}")
