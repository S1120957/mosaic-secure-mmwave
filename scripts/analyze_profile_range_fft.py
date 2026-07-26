from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


N_SUBFRAMES = 2_000
N_CHIRPS = 16
N_ADC = 256
N_RX = 4
COMPLEX_COMPONENTS = 2
INT16_PER_SUBFRAME = N_CHIRPS * N_ADC * N_RX * COMPLEX_COMPONENTS
BYTES_PER_SUBFRAME = INT16_PER_SUBFRAME * 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_size(path: Path) -> None:
    expected = N_SUBFRAMES * BYTES_PER_SUBFRAME
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(f"{path}: expected {expected} bytes, found {actual}")


def decode_subframe(raw: np.ndarray) -> np.ndarray:
    """
    Decode one subframe using the repository's established layout:

        [chirp, adc_sample, rx, component]

    where component 0 is Q and component 1 is I, yielding I + jQ.
    """
    values = raw.reshape(N_CHIRPS, N_ADC, N_RX, COMPLEX_COMPONENTS)
    q = values[..., 0].astype(np.float32)
    i = values[..., 1].astype(np.float32)
    return i + 1j * q


def profile_range_power(path: Path, profile_parity: int) -> np.ndarray:
    validate_size(path)

    raw = np.memmap(
        path,
        dtype="<i2",
        mode="r",
        shape=(N_SUBFRAMES, INT16_PER_SUBFRAME),
    )

    selected = np.arange(profile_parity, N_SUBFRAMES, 2)
    accumulator = np.zeros(N_ADC // 2, dtype=np.float64)
    window = np.hanning(N_ADC).astype(np.float32)

    for index in selected:
        cube = decode_subframe(raw[index])

        # Remove per-chirp/RX DC before the range FFT.
        cube = cube - cube.mean(axis=1, keepdims=True)
        spectrum = np.fft.fft(cube * window[None, :, None], axis=1)
        power = np.abs(spectrum[:, : N_ADC // 2, :]) ** 2

        accumulator += power.mean(axis=(0, 2))

    return accumulator / selected.size


def summarize_difference(target_power: np.ndarray, background_power: np.ndarray) -> dict:
    eps = np.finfo(np.float64).tiny
    difference = target_power - background_power
    ratio = target_power / np.maximum(background_power, eps)

    positive = np.maximum(difference, 0.0)
    positive_total = float(positive.sum())

    dominant_difference_bin = int(np.argmax(difference))
    dominant_ratio_bin = int(np.argmax(ratio))

    if positive_total > 0:
        normalized = positive / positive_total
        cumulative = np.cumsum(normalized)
        bins_50 = int(np.searchsorted(cumulative, 0.50))
        bins_90 = int(np.searchsorted(cumulative, 0.90))
    else:
        bins_50 = None
        bins_90 = None

    top_bins = np.argsort(difference)[-10:][::-1]

    return {
        "target_total_power": float(target_power.sum()),
        "background_total_power": float(background_power.sum()),
        "total_power_ratio": float(
            target_power.sum() / max(background_power.sum(), eps)
        ),
        "dominant_difference_bin": dominant_difference_bin,
        "dominant_difference_value": float(difference[dominant_difference_bin]),
        "dominant_ratio_bin": dominant_ratio_bin,
        "dominant_ratio": float(ratio[dominant_ratio_bin]),
        "positive_difference_energy": positive_total,
        "positive_difference_cumulative_50_percent_bin": bins_50,
        "positive_difference_cumulative_90_percent_bin": bins_90,
        "top_difference_bins": [
            {
                "bin": int(bin_index),
                "target_power": float(target_power[bin_index]),
                "background_power": float(background_power[bin_index]),
                "difference": float(difference[bin_index]),
                "ratio": float(ratio[bin_index]),
            }
            for bin_index in top_bins
        ],
    }


def analyze_session(session_dir: Path) -> dict:
    target = session_dir / "profile_switch_target_full.bin"
    background = session_dir / "profile_switch_bg_full.bin"

    for path in (target, background):
        if not path.exists():
            raise FileNotFoundError(path)

    profiles = {}
    for parity, profile_name in ((0, "P0_even_subframes"), (1, "P1_odd_subframes")):
        target_power = profile_range_power(target, parity)
        background_power = profile_range_power(background, parity)

        profiles[profile_name] = {
            "subframes_per_condition": N_SUBFRAMES // 2,
            "range_bins_analyzed": N_ADC // 2,
            "summary": summarize_difference(target_power, background_power),
            "target_mean_range_power": target_power.tolist(),
            "background_mean_range_power": background_power.tolist(),
        }

    return {
        "session_id": session_dir.name,
        "target_sha256": sha256(target),
        "background_sha256": sha256(background),
        "decoder": {
            "shape": [N_CHIRPS, N_ADC, N_RX],
            "component_order": "Q_then_I",
            "logical_complex_sample": "I_plus_jQ",
            "range_fft_bins_retained": N_ADC // 2,
        },
        "profiles": profiles,
    }


def relative_difference_percent(a: float, b: float) -> float:
    denominator = (abs(a) + abs(b)) / 2.0
    return 0.0 if denominator == 0 else abs(a - b) / denominator * 100.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session02", type=Path)
    parser.add_argument("session03", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    session02 = analyze_session(args.session02)
    session03 = analyze_session(args.session03)

    repeatability = {}
    for profile in ("P0_even_subframes", "P1_odd_subframes"):
        s2 = session02["profiles"][profile]["summary"]
        s3 = session03["profiles"][profile]["summary"]

        repeatability[profile] = {
            "session02_total_power_ratio": s2["total_power_ratio"],
            "session03_total_power_ratio": s3["total_power_ratio"],
            "total_power_ratio_drift_percent": relative_difference_percent(
                s2["total_power_ratio"], s3["total_power_ratio"]
            ),
            "session02_dominant_difference_bin": s2["dominant_difference_bin"],
            "session03_dominant_difference_bin": s3["dominant_difference_bin"],
            "dominant_bin_match": (
                s2["dominant_difference_bin"] == s3["dominant_difference_bin"]
            ),
        }

    report = {
        "report_type": "profile_stratified_range_fft_analysis",
        "publication_eligibility": False,
        "limitations": [
            "Session 03 lacks a distinct matching timestamp artifact.",
            "Even subframes are treated as P0 and odd subframes as P1.",
            "The decoder assumes the established Q-then-I DCA1000 layout.",
            "FFT-bin indices are reported without conversion to physical range.",
            "This analysis does not establish acquisition provenance or challenge authenticity.",
        ],
        "sessions": {
            "session02": session02,
            "session03": session03,
        },
        "cross_session_repeatability": repeatability,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    compact = {
        "report_type": report["report_type"],
        "publication_eligibility": report["publication_eligibility"],
        "cross_session_repeatability": repeatability,
    }
    print(json.dumps(compact, indent=2))
    print(f"\nWritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
