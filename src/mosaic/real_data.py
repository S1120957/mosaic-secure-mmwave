from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from mosaic.adapters.ti_iwr6843 import DCA1000BinaryReader, TIRawCaptureConfig


C0 = 299_792_458.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_profile(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Profile must be a YAML mapping")
    return data


def raw_config_from_profile(profile: dict[str, Any]) -> TIRawCaptureConfig:
    rf = profile["rf_profile"]
    return TIRawCaptureConfig(
        adc_samples=int(rf["adc_samples"]),
        chirps_per_frame=int(rf["chirps_per_frame"]),
        rx_channels=bin(int(rf["rx_mask"])).count("1"),
        adc_bits=int(rf["adc_bits"]),
        complex_samples=str(rf["adc_format"]).lower() == "complex",
        iq_order=str(rf["iq_order"]),
        sample_order=str(rf.get("sample_order", "chirp_sample_rx")),
        lane_interleave=bool(rf["lane_interleave"]),
        scale_to_unit=bool(rf.get("scale_to_unit", False)),
    )


def mean_range_power(
    reader: DCA1000BinaryReader,
    *,
    fft_window: str = "hann",
) -> np.ndarray:
    frames = [frame.samples for frame in reader.frames()]
    cube = np.stack(frames, axis=0)
    adc_samples = cube.shape[2]
    if fft_window == "hann":
        window = np.hanning(adc_samples)[None, None, :, None]
    elif fft_window == "rectangular":
        window = np.ones((1, 1, adc_samples, 1), dtype=np.float64)
    else:
        raise ValueError("fft_window must be hann or rectangular")
    spectrum = np.fft.fft(cube * window, axis=2)
    positive = spectrum[:, :, : adc_samples // 2, :]
    return np.mean(np.abs(positive) ** 2, axis=(0, 1, 3))


def range_axis_m(profile: dict[str, Any]) -> np.ndarray:
    rf = profile["rf_profile"]
    n = int(rf["adc_samples"])
    fs = float(rf["adc_sample_rate_ksps"]) * 1e3
    slope = float(rf["frequency_slope_mhz_per_us"]) * 1e12
    bins = np.arange(n // 2, dtype=np.float64)
    beat_hz = bins * fs / n
    return C0 * beat_hz / (2.0 * slope)


def verify_real_capture_pair(
    *,
    profile_path: Path,
    output_report: Path,
    output_spectrum_csv: Path,
) -> dict[str, Any]:
    profile = load_profile(profile_path)
    capture = profile["capture"]
    verification = profile["verification"]
    raw_cfg = raw_config_from_profile(profile)

    target_path = Path(capture["target_bin"])
    background_path = Path(capture["background_bin"])
    gt_path = Path(capture["ground_truth_manifest"])

    target_sha = sha256_file(target_path)
    background_sha = sha256_file(background_path)
    target_reader = DCA1000BinaryReader(target_path, raw_cfg)
    background_reader = DCA1000BinaryReader(background_path, raw_cfg)

    target_power = mean_range_power(
        target_reader, fft_window=str(verification["fft_window"])
    )
    background_power = mean_range_power(
        background_reader, fft_window=str(verification["fft_window"])
    )
    differential = np.maximum(target_power - background_power, 0.0)
    ranges = range_axis_m(profile)

    output_spectrum_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_spectrum_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "range_bin",
                "range_m",
                "target_power",
                "background_power",
                "differential_power",
            ]
        )
        for index in range(len(ranges)):
            writer.writerow(
                [
                    index,
                    f"{ranges[index]:.9f}",
                    f"{target_power[index]:.9f}",
                    f"{background_power[index]:.9f}",
                    f"{differential[index]:.9f}",
                ]
            )

    expected_results = []
    all_targets_pass = True
    for expected in verification["expected_targets"]:
        bin_index = int(expected["expected_range_bin"])
        surveyed = float(expected["surveyed_range_m"])
        estimated = float(ranges[bin_index])
        error = abs(estimated - surveyed)
        tolerance = float(expected["tolerance_m"])
        local_start = max(0, bin_index - 1)
        local_end = min(len(differential), bin_index + 2)
        local_peak = int(
            np.argmax(differential[local_start:local_end]) + local_start
        )
        passed = local_peak == bin_index and error <= tolerance
        all_targets_pass = all_targets_pass and passed
        expected_results.append(
            {
                "target_id": str(expected["target_id"]),
                "expected_range_bin": bin_index,
                "observed_local_peak_bin": local_peak,
                "estimated_range_m": estimated,
                "surveyed_range_m": surveyed,
                "absolute_error_m": error,
                "tolerance_m": tolerance,
                "passed": passed,
            }
        )

    strongest_bins = np.argsort(differential)[::-1][:10]
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    expected_size = int(capture["expected_file_size_bytes"])
    report = {
        "dataset_id": "iwr6843-dca1000-session01",
        "hardware": profile["hardware"],
        "capture_layout": {
            "frames_target": target_reader.frame_count(),
            "frames_background": background_reader.frame_count(),
            "chirps_per_frame": raw_cfg.chirps_per_frame,
            "adc_samples": raw_cfg.adc_samples,
            "rx_channels": raw_cfg.rx_channels,
            "logical_shape_per_frame": [
                raw_cfg.chirps_per_frame,
                raw_cfg.adc_samples,
                raw_cfg.rx_channels,
            ],
            "bytes_per_frame": raw_cfg.bytes_per_frame,
            "target_file_size_bytes": target_path.stat().st_size,
            "background_file_size_bytes": background_path.stat().st_size,
            "target_size_valid": target_path.stat().st_size == expected_size,
            "background_size_valid": background_path.stat().st_size == expected_size,
            "iq_order": raw_cfg.iq_order,
            "sample_order": raw_cfg.sample_order,
            "logical_complex_value": "I + jQ",
        },
        "integrity": {
            "target_sha256": target_sha,
            "target_sha256_expected": capture["target_sha256"],
            "target_sha256_valid": target_sha == capture["target_sha256"],
            "background_sha256": background_sha,
            "background_sha256_expected": capture["background_sha256"],
            "background_sha256_valid": (
                background_sha == capture["background_sha256"]
            ),
        },
        "processing": {
            "fft_window": verification["fft_window"],
            "target_minus_background": bool(
                verification["target_minus_background"]
            ),
            "range_bin_width_m": float(ranges[1] - ranges[0]),
            "strongest_differential_bins": [
                {
                    "range_bin": int(index),
                    "range_m": float(ranges[index]),
                    "differential_power": float(differential[index]),
                }
                for index in strongest_bins
            ],
        },
        "ground_truth": gt,
        "target_checks": expected_results,
        "challenge_profile_identity": {
            "status": profile["challenge"]["status"],
            "note": profile["challenge"]["note"].strip(),
            "verified_for_this_capture": False,
        },
    }

    report["overall_pass"] = all(
        [
            report["capture_layout"]["target_size_valid"],
            report["capture_layout"]["background_size_valid"],
            report["integrity"]["target_sha256_valid"],
            report["integrity"]["background_sha256_valid"],
            target_reader.frame_count() == int(capture["expected_frames"]),
            background_reader.frame_count() == int(capture["expected_frames"]),
            all_targets_pass,
        ]
    )

    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
