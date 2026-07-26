from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


BYTES_PER_SUBFRAME = 65_536
SAMPLES_PER_SUBFRAME = BYTES_PER_SUBFRAME // 2
EXPECTED_SUBFRAMES = 2_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frames(path: Path) -> np.memmap:
    size = path.stat().st_size
    expected = BYTES_PER_SUBFRAME * EXPECTED_SUBFRAMES
    if size != expected:
        raise ValueError(f"{path}: expected {expected} bytes, found {size}")
    return np.memmap(
        path,
        dtype="<i2",
        mode="r",
        shape=(EXPECTED_SUBFRAMES, SAMPLES_PER_SUBFRAME),
    )


def frame_metrics(frames: np.ndarray) -> dict[str, np.ndarray]:
    x = np.asarray(frames, dtype=np.float64)
    return {
        "mean": x.mean(axis=1),
        "std": x.std(axis=1),
        "rms": np.sqrt(np.mean(np.square(x), axis=1)),
        "mean_abs": np.mean(np.abs(x), axis=1),
        "peak_abs": np.max(np.abs(x), axis=1),
    }


def summarize(values: np.ndarray) -> dict[str, float]:
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "max": float(np.max(values)),
    }


def standardized_effect(target: np.ndarray, background: np.ndarray) -> float | None:
    n1 = target.size
    n0 = background.size
    if n1 < 2 or n0 < 2:
        return None
    pooled = np.sqrt(
        ((n1 - 1) * np.var(target, ddof=1) + (n0 - 1) * np.var(background, ddof=1))
        / (n1 + n0 - 2)
    )
    return float((np.mean(target) - np.mean(background)) / pooled) if pooled else None


def profile_report(target: np.ndarray, background: np.ndarray, indices: np.ndarray) -> dict:
    target_metrics = frame_metrics(target[indices])
    background_metrics = frame_metrics(background[indices])

    report: dict[str, object] = {
        "subframes": int(indices.size),
        "metrics": {},
    }

    for name in target_metrics:
        t = target_metrics[name]
        b = background_metrics[name]
        report["metrics"][name] = {
            "target": summarize(t),
            "background": summarize(b),
            "target_minus_background_mean": float(np.mean(t) - np.mean(b)),
            "target_to_background_ratio": (
                float(np.mean(t) / np.mean(b)) if np.mean(b) != 0 else None
            ),
            "standardized_effect": standardized_effect(t, b),
        }

    return report


def session_report(session_dir: Path) -> dict:
    target_path = session_dir / "profile_switch_target_full.bin"
    background_path = session_dir / "profile_switch_bg_full.bin"

    for path in (target_path, background_path):
        if not path.exists():
            raise FileNotFoundError(path)

    target = load_frames(target_path)
    background = load_frames(background_path)

    p0 = np.arange(0, EXPECTED_SUBFRAMES, 2)
    p1 = np.arange(1, EXPECTED_SUBFRAMES, 2)

    return {
        "session_id": session_dir.name,
        "target_sha256": sha256(target_path),
        "background_sha256": sha256(background_path),
        "analysis_scope": (
            "Raw int16 profile-stratified statistics only; this does not decode "
            "physical range, Doppler, angle, or challenge identity."
        ),
        "profiles": {
            "P0_even_subframes": profile_report(target, background, p0),
            "P1_odd_subframes": profile_report(target, background, p1),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session02", type=Path)
    parser.add_argument("session03", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    s2 = session_report(args.session02)
    s3 = session_report(args.session03)

    report = {
        "report_type": "profile_stratified_raw_signal_analysis",
        "publication_eligibility": False,
        "limitations": [
            "Session 03 lacks a distinct matching timestamp artifact.",
            "The analysis treats even subframes as P0 and odd subframes as P1.",
            "Metrics are computed on raw little-endian int16 samples.",
            "No physical range, Doppler, angle, or waveform claim is made.",
        ],
        "sessions": {
            "session02": s2,
            "session03": s3,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
