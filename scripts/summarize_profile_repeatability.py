from __future__ import annotations

import argparse
import json
from pathlib import Path


METRICS = ("rms", "mean_abs", "peak_abs")


def get_metric(report: dict, session: str, profile: str, metric: str) -> dict:
    return report["sessions"][session]["profiles"][profile]["metrics"][metric]


def rel_diff_percent(a: float, b: float) -> float:
    denom = (abs(a) + abs(b)) / 2.0
    return 0.0 if denom == 0 else abs(a - b) / denom * 100.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.input_json.read_text(encoding="utf-8"))
    profiles = ("P0_even_subframes", "P1_odd_subframes")

    summary = {
        "report_type": "profile_repeatability_summary",
        "source_report": args.input_json.as_posix(),
        "publication_eligibility": False,
        "limitations": report.get("limitations", []),
        "metrics": {},
    }

    for metric in METRICS:
        metric_summary = {}
        for profile in profiles:
            s2 = get_metric(report, "session02", profile, metric)
            s3 = get_metric(report, "session03", profile, metric)

            s2_delta = float(s2["target_minus_background_mean"])
            s3_delta = float(s3["target_minus_background_mean"])
            s2_ratio = float(s2["target_to_background_ratio"])
            s3_ratio = float(s3["target_to_background_ratio"])

            metric_summary[profile] = {
                "session02_target_minus_background": s2_delta,
                "session03_target_minus_background": s3_delta,
                "cross_session_delta_drift_percent": rel_diff_percent(s2_delta, s3_delta),
                "session02_target_to_background_ratio": s2_ratio,
                "session03_target_to_background_ratio": s3_ratio,
                "cross_session_ratio_drift_percent": rel_diff_percent(s2_ratio, s3_ratio),
            }

        p0_s2 = metric_summary["P0_even_subframes"]["session02_target_minus_background"]
        p1_s2 = metric_summary["P1_odd_subframes"]["session02_target_minus_background"]
        p0_s3 = metric_summary["P0_even_subframes"]["session03_target_minus_background"]
        p1_s3 = metric_summary["P1_odd_subframes"]["session03_target_minus_background"]

        metric_summary["profile_balance"] = {
            "session02_P0_vs_P1_drift_percent": rel_diff_percent(p0_s2, p1_s2),
            "session03_P0_vs_P1_drift_percent": rel_diff_percent(p0_s3, p1_s3),
        }

        summary["metrics"][metric] = metric_summary

    checks = []
    for metric, data in summary["metrics"].items():
        for profile in profiles:
            checks.append(data[profile]["cross_session_delta_drift_percent"] < 1.0)
            checks.append(data[profile]["cross_session_ratio_drift_percent"] < 1.0)
        checks.append(data["profile_balance"]["session02_P0_vs_P1_drift_percent"] < 1.0)
        checks.append(data["profile_balance"]["session03_P0_vs_P1_drift_percent"] < 1.0)

    summary["repeatability_check"] = {
        "threshold_percent": 1.0,
        "all_selected_metrics_within_threshold": all(checks),
        "status": "PASS" if all(checks) else "REVIEW",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
