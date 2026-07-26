from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


EXPECTED_SIZE = 131_072_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_int16(path: Path) -> np.memmap:
    return np.memmap(path, dtype="<i2", mode="r")


def compare_files(first: Path, second: Path) -> dict:
    a = load_int16(first)
    b = load_int16(second)

    if a.size != b.size:
        raise ValueError(f"Sample-count mismatch: {first} vs {second}")

    sample_count = int(a.size)
    chunk_samples = 4_000_000

    equal_samples = 0
    absolute_difference_sum = 0.0
    squared_difference_sum = 0.0

    sum_a = 0.0
    sum_b = 0.0
    sum_a2 = 0.0
    sum_b2 = 0.0
    sum_ab = 0.0

    for start in range(0, sample_count, chunk_samples):
        stop = min(start + chunk_samples, sample_count)

        x = np.asarray(a[start:stop], dtype=np.float64)
        y = np.asarray(b[start:stop], dtype=np.float64)
        difference = x - y

        equal_samples += int(np.count_nonzero(x == y))
        absolute_difference_sum += float(np.abs(difference).sum())
        squared_difference_sum += float(np.square(difference).sum())

        sum_a += float(x.sum())
        sum_b += float(y.sum())
        sum_a2 += float(np.square(x).sum())
        sum_b2 += float(np.square(y).sum())
        sum_ab += float((x * y).sum())

    mean_a = sum_a / sample_count
    mean_b = sum_b / sample_count

    covariance = (sum_ab / sample_count) - (mean_a * mean_b)
    variance_a = (sum_a2 / sample_count) - (mean_a**2)
    variance_b = (sum_b2 / sample_count) - (mean_b**2)

    denominator = max(variance_a * variance_b, 0.0) ** 0.5
    correlation = covariance / denominator if denominator else None

    return {
        "first_file": first.as_posix(),
        "second_file": second.as_posix(),
        "sample_count": sample_count,
        "identical_sample_fraction": equal_samples / sample_count,
        "mean_absolute_difference": absolute_difference_sum / sample_count,
        "root_mean_squared_difference": (
            squared_difference_sum / sample_count
        ) ** 0.5,
        "pearson_correlation": correlation,
    }


def session_record(directory: Path) -> dict:
    target = directory / "profile_switch_target_full.bin"
    background = directory / "profile_switch_bg_full.bin"

    for path in (target, background):
        if not path.exists():
            raise FileNotFoundError(path)

    return {
        "directory": directory.as_posix(),
        "target": {
            "size_bytes": target.stat().st_size,
            "size_valid": target.stat().st_size == EXPECTED_SIZE,
            "sha256": sha256(target),
        },
        "background": {
            "size_bytes": background.stat().st_size,
            "size_valid": background.stat().st_size == EXPECTED_SIZE,
            "sha256": sha256(background),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session02", type=Path)
    parser.add_argument("session03", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    session02 = session_record(args.session02)
    session03 = session_record(args.session03)

    report = {
        "report_type": "cross_session_binary_repeatability",
        "publication_eligibility": False,
        "limitations": [
            "Session 03 does not have a distinct matching timestamp artifact.",
            "This report compares retained binary contents only.",
            "It does not establish complete Session 03 acquisition provenance.",
        ],
        "sessions": {
            "session02": session02,
            "session03": session03,
        },
        "independence_checks": {
            "target_hashes_distinct": (
                session02["target"]["sha256"]
                != session03["target"]["sha256"]
            ),
            "background_hashes_distinct": (
                session02["background"]["sha256"]
                != session03["background"]["sha256"]
            ),
        },
        "comparisons": {
            "target_session02_vs_session03": compare_files(
                args.session02 / "profile_switch_target_full.bin",
                args.session03 / "profile_switch_target_full.bin",
            ),
            "background_session02_vs_session03": compare_files(
                args.session02 / "profile_switch_bg_full.bin",
                args.session03 / "profile_switch_bg_full.bin",
            ),
            "session02_target_vs_background": compare_files(
                args.session02 / "profile_switch_target_full.bin",
                args.session02 / "profile_switch_bg_full.bin",
            ),
            "session03_target_vs_background": compare_files(
                args.session03 / "profile_switch_target_full.bin",
                args.session03 / "profile_switch_bg_full.bin",
            ),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print(f"\nWritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
