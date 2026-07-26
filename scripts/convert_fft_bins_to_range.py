from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

C_M_S = 299_792_458.0


def parse_profiles(cfg_path: Path) -> dict[str, dict[str, float]]:
    profiles: dict[str, dict[str, float]] = {}

    for raw_line in cfg_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("%", 1)[0].strip()
        if not line.startswith("profileCfg "):
            continue

        fields = line.split()
        if len(fields) < 12:
            raise ValueError(f"Malformed profileCfg line: {raw_line}")

        profile_id = fields[1]
        start_frequency_ghz = float(fields[2])
        frequency_slope_mhz_us = float(fields[8])
        adc_samples = int(fields[10])
        sample_rate_ksps = float(fields[11])

        profiles[profile_id] = {
            "start_frequency_ghz": start_frequency_ghz,
            "frequency_slope_mhz_per_us": frequency_slope_mhz_us,
            "adc_samples": adc_samples,
            "sample_rate_ksps": sample_rate_ksps,
        }

    if not profiles:
        raise ValueError(f"No profileCfg lines found in {cfg_path}")

    return profiles


def derive_profile_metrics(profile: dict[str, float]) -> dict[str, float]:
    slope_hz_s = profile["frequency_slope_mhz_per_us"] * 1e12
    sample_rate_hz = profile["sample_rate_ksps"] * 1e3
    adc_samples = int(profile["adc_samples"])
    adc_sampling_time_s = adc_samples / sample_rate_hz
    sweep_bandwidth_hz = slope_hz_s * adc_sampling_time_s
    range_resolution_m = C_M_S / (2.0 * sweep_bandwidth_hz)
    range_bin_spacing_m = C_M_S * sample_rate_hz / (
        2.0 * slope_hz_s * adc_samples
    )
    max_positive_fft_range_m = range_bin_spacing_m * (adc_samples // 2 - 1)

    return {
        **profile,
        "frequency_slope_hz_per_s": slope_hz_s,
        "sample_rate_hz": sample_rate_hz,
        "adc_sampling_time_us": adc_sampling_time_s * 1e6,
        "sweep_bandwidth_hz": sweep_bandwidth_hz,
        "range_resolution_m": range_resolution_m,
        "range_bin_spacing_m": range_bin_spacing_m,
        "max_reported_positive_fft_range_m": max_positive_fft_range_m,
    }


def profile_number(name: str) -> str:
    match = re.match(r"P(\d+)_", name)
    if not match:
        raise ValueError(f"Cannot resolve profile from {name}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("range_fft_report", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.range_fft_report.read_text(encoding="utf-8"))
    parsed = parse_profiles(args.config)
    derived = {pid: derive_profile_metrics(p) for pid, p in parsed.items()}

    converted: dict[str, object] = {}
    for profile_name, values in source["cross_session_repeatability"].items():
        pid = profile_number(profile_name)
        if pid not in derived:
            raise KeyError(f"Profile {pid} is missing from configuration")

        spacing = derived[pid]["range_bin_spacing_m"]
        bin02 = int(values["session02_dominant_difference_bin"])
        bin03 = int(values["session03_dominant_difference_bin"])

        converted[profile_name] = {
            **values,
            "range_bin_spacing_m": spacing,
            "session02_dominant_difference_range_m": bin02 * spacing,
            "session03_dominant_difference_range_m": bin03 * spacing,
            "dominant_range_match": bin02 == bin03,
        }

    report = {
        "report_type": "physical_range_conversion",
        "source_range_fft_report": args.range_fft_report.as_posix(),
        "source_config": args.config.as_posix(),
        "publication_eligibility": False,
        "formulae": {
            "sweep_bandwidth": "B = slope * (N_adc / sample_rate)",
            "range_resolution": "delta_R = c / (2B)",
            "range_bin_spacing": "delta_R_bin = c * sample_rate / (2 * slope * N_fft)",
            "dominant_range": "R_bin = bin_index * delta_R_bin",
        },
        "profile_parameters": derived,
        "dominant_bin_conversion": converted,
        "limitations": [
            "Session 03 lacks a distinct matching timestamp artifact.",
            "The conversion assumes N_fft equals the 256 ADC samples used by the source FFT analysis.",
            "Reported values are beat-frequency range-bin locations, not independently surveyed target distances.",
            "No calibration correction for antenna, cable, ADC, or fixed hardware delay is applied.",
            "Publication eligibility remains false until acquisition provenance and ground truth are complete.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    compact = {
        "report_type": report["report_type"],
        "publication_eligibility": False,
        "profile_parameters": {
            pid: {
                "range_resolution_m": value["range_resolution_m"],
                "range_bin_spacing_m": value["range_bin_spacing_m"],
            }
            for pid, value in derived.items()
        },
        "dominant_bin_conversion": converted,
    }
    print(json.dumps(compact, indent=2))
    print(f"\nWritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
