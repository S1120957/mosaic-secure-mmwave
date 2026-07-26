from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import yaml

from mosaic.signal_processing import synthetic_fmcw_buffer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("configs/ti_iwr6843isk_ods_single_anchor.yaml"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=12)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.profile.read_text(encoding="utf-8"))
    rf = cfg["rf_profile"]
    gt = cfg["ground_truth"]
    rng = np.random.default_rng(6843)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as handle:
        for _ in range(args.frames):
            samples = synthetic_fmcw_buffer(
                range_m=float(gt["target_position_m"][0]),
                radial_velocity_mps=float(gt["target_velocity_mps"][0]),
                bearing_rad=0.0,
                frames=int(rf["chirps_per_frame"]),
                fast_time_samples=int(rf["adc_samples"]),
                antennas=bin(int(rf["rx_mask"])).count("1"),
                rng=rng,
            )
            # Encode proxy real samples as complex IQ int16 in logical order.
            i = np.clip(samples * 12000, -32768, 32767).astype("<i2")
            q = np.zeros_like(i, dtype="<i2")
            interleaved = np.stack([i, q], axis=-1).reshape(-1)
            interleaved.tofile(handle)

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
