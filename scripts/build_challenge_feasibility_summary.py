from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary-repeatability", type=Path, required=True)
    parser.add_argument("--profile-repeatability", type=Path, required=True)
    parser.add_argument("--range-fft", type=Path, required=True)
    parser.add_argument("--range-conversion", type=Path, required=True)
    parser.add_argument("--session03-status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    binary = load(args.binary_repeatability)
    profile = load(args.profile_repeatability)
    range_fft = load(args.range_fft)
    range_conversion = load(args.range_conversion)
    session03 = load(args.session03_status)

    p0_fft = range_fft["cross_session_repeatability"]["P0_even_subframes"]
    p1_fft = range_fft["cross_session_repeatability"]["P1_odd_subframes"]
    p0_range = range_conversion["dominant_bin_conversion"]["P0_even_subframes"]
    p1_range = range_conversion["dominant_bin_conversion"]["P1_odd_subframes"]

    report = {
        "report_type": "challenge_feasibility_evidence_summary",
        "publication_eligibility": False,
        "evidence_status": {
            "binary_file_distinction": {
                "status": "PASS",
                "target_hashes_distinct": binary["independence_checks"][
                    "target_hashes_distinct"
                ],
                "background_hashes_distinct": binary["independence_checks"][
                    "background_hashes_distinct"
                ],
            },
            "raw_signal_repeatability": {
                "status": profile["repeatability_check"]["status"],
                "threshold_percent": profile["repeatability_check"][
                    "threshold_percent"
                ],
                "all_selected_metrics_within_threshold": profile[
                    "repeatability_check"
                ]["all_selected_metrics_within_threshold"],
            },
            "range_fft_repeatability": {
                "status": (
                    "PASS"
                    if p0_fft["dominant_bin_match"]
                    and p1_fft["dominant_bin_match"]
                    else "REVIEW"
                ),
                "P0": {
                    "dominant_bin": p0_fft["session02_dominant_difference_bin"],
                    "dominant_bin_match": p0_fft["dominant_bin_match"],
                    "total_power_ratio_drift_percent": p0_fft[
                        "total_power_ratio_drift_percent"
                    ],
                },
                "P1": {
                    "dominant_bin": p1_fft["session02_dominant_difference_bin"],
                    "dominant_bin_match": p1_fft["dominant_bin_match"],
                    "total_power_ratio_drift_percent": p1_fft[
                        "total_power_ratio_drift_percent"
                    ],
                },
            },
            "uncalibrated_range_bin_conversion": {
                "status": "PASS",
                "range_bin_spacing_m": p0_range["range_bin_spacing_m"],
                "P0_dominant_bin_location_m": p0_range[
                    "session02_dominant_difference_range_m"
                ],
                "P1_dominant_bin_location_m": p1_range[
                    "session02_dominant_difference_range_m"
                ],
            },
            "session03_provenance": {
                "status": "BLOCKED",
                "timestamp_file_status": session03["timestamp_file_status"],
                "timestamp_validation": session03["timestamp_validation"],
                "publication_eligibility": session03["publication_eligibility"],
            },
        },
        "defensible_claims": [
            "The retained Session 02 and Session 03 binary files are distinct by SHA-256.",
            "Selected raw-signal target/background metrics are repeatable under the predefined one-percent drift rule.",
            "The dominant target-minus-background FFT bin is reproduced across the retained binary sets for both profiles.",
            "The reported metric locations are uncalibrated beat-frequency range-bin locations.",
        ],
        "claims_not_supported": [
            "Complete independent Session 03 acquisition provenance.",
            "Verified Session 03 packet-loss or timestamp continuity.",
            "Independently surveyed physical target distance.",
            "Challenge authenticity or security against an active adversary.",
            "Publication eligibility of Session 03.",
        ],
        "source_files": {
            "binary_repeatability": args.binary_repeatability.as_posix(),
            "profile_repeatability": args.profile_repeatability.as_posix(),
            "range_fft": args.range_fft.as_posix(),
            "range_conversion": args.range_conversion.as_posix(),
            "session03_status": args.session03_status.as_posix(),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nWritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
