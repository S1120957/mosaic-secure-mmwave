from __future__ import annotations
import argparse
import json
from pathlib import Path

EXPECTED = 2000
BYTES_PER_SUBFRAME = 65536

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("timestamps", type=Path)
    args = p.parse_args()

    rows = json.loads(args.timestamps.read_text(encoding="utf-8"))
    if len(rows) != EXPECTED:
        raise SystemExit(f"Expected {EXPECTED} rows, found {len(rows)}")

    for i, row in enumerate(rows):
        expected_profile = "P0" if i % 2 == 0 else "P1"
        if row.get("subframe_index") != i:
            raise SystemExit(f"subframe_index mismatch at row {i}")
        if row.get("advanced_frame_index") != i // 2:
            raise SystemExit(f"advanced_frame_index mismatch at row {i}")
        if row.get("profile_id") != expected_profile:
            raise SystemExit(f"profile_id mismatch at row {i}")
        if row.get("bytes_received") != (i + 1) * BYTES_PER_SUBFRAME:
            raise SystemExit(f"bytes_received mismatch at row {i}")
        if not isinstance(row.get("timestamp_ns"), int):
            raise SystemExit(f"timestamp_ns missing or invalid at row {i}")

    print(json.dumps({
        "rows": len(rows),
        "alternation_valid": True,
        "byte_accounting_valid": True,
        "timestamps_present": True
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
