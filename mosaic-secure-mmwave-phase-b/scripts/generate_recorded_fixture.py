from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.geometry import predict
from mosaic.models import AnchorConfig
from mosaic.recording import GroundTruthState, RecordingMetadata, RecordingWriter
from mosaic.signal_processing import synthetic_fmcw_buffer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/synthetic.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/recorded/synthetic-fixture"))
    parser.add_argument("--epochs", type=int, default=12)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    rng = np.random.default_rng(int(cfg["seed"]))

    anchors: dict[str, AnchorConfig] = {}
    keys: dict[str, bytes] = {}
    for item in cfg["anchors"]:
        anchor = AnchorConfig(
            anchor_id=item["id"],
            position_m=tuple(item["position_m"]),
            key_hex=item["key_hex"],
        )
        anchors[anchor.anchor_id] = anchor
        keys[anchor.anchor_id] = bytes.fromhex(anchor.key_hex)

    codebook = ChallengeCodebook(
        tuple(cfg["challenge"]["start_frequency_offsets_hz"]),
        tuple(cfg["challenge"]["chirp_slopes_hz_per_s"]),
        tuple(tuple(x) for x in cfg["challenge"]["chirp_permutations"]),
    )

    metadata = RecordingMetadata(
        recording_id=args.output.name,
        created_utc=datetime.now(timezone.utc).isoformat(),
        source="synthetic-recorded-fixture",
        radar_model="proxy-fmcw-v1",
        firmware_version="sim-1.0",
        sample_rate_hz=2_000_000,
        channels=4,
        notes="Synthetic proxy buffer for validating the recorded-data pipeline.",
    )
    writer = RecordingWriter(args.output, metadata)

    position = np.asarray(cfg["scenario"]["initial_position_m"], dtype=float)
    velocity = np.asarray(cfg["scenario"]["velocity_mps"], dtype=float)
    dt = float(cfg["dt_seconds"])

    for epoch in range(args.epochs):
        for anchor_id, anchor in anchors.items():
            challenge = derive_challenge(
                key=keys[anchor_id],
                anchor_id=anchor_id,
                epoch=epoch,
                codebook=codebook,
            )
            r, rv, bearing = predict(anchor.position_m, position, velocity)
            samples = synthetic_fmcw_buffer(
                range_m=r,
                radial_velocity_mps=rv,
                bearing_rad=bearing,
                rng=rng,
            )
            writer.append(
                frame_id=f"{anchor_id}-e{epoch:06d}",
                anchor_id=anchor_id,
                epoch=epoch,
                timestamp_ns=int(epoch * dt * 1e9),
                challenge=challenge,
                samples=samples,
                ground_truth=GroundTruthState(
                    position_m=tuple(position),
                    velocity_mps=tuple(velocity),
                ),
            )
        position = position + velocity * dt

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
