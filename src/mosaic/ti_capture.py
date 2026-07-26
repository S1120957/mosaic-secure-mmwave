from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from mosaic.adapters.ti_iwr6843 import (
    DCA1000BinaryReader,
    TIRawCaptureConfig,
    estimate_ti_observation,
)
from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.models import AnchorConfig
from mosaic.recording import (
    GroundTruthState,
    RecordingMetadata,
    RecordingWriter,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_ti_profile(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("TI profile must be a YAML mapping")
    return data


def import_dca1000_recording(
    *,
    profile_path: Path,
    source_bin: Path | None = None,
    output_root: Path | None = None,
    anchor_key_hex: str,
) -> dict[str, Any]:
    cfg = load_ti_profile(profile_path)
    hardware = cfg["hardware"]
    rf = cfg["rf_profile"]
    capture = cfg["capture"]
    gt = cfg["ground_truth"]
    challenge_cfg = cfg["challenge"]

    source_bin = source_bin or Path(capture["source_bin"])
    output_root = output_root or Path(capture["output_recording"])

    raw_config = TIRawCaptureConfig(
        adc_samples=int(rf["adc_samples"]),
        chirps_per_frame=int(rf["chirps_per_frame"]),
        rx_channels=int(bin(int(rf["rx_mask"])).count("1")),
        adc_bits=int(rf["adc_bits"]),
        complex_samples=str(rf["adc_format"]).lower() == "complex",
        iq_order=str(rf["iq_order"]),
        lane_interleave=bool(rf["lane_interleave"]),
    )
    reader = DCA1000BinaryReader(source_bin, raw_config)
    frame_count = reader.frame_count()

    is_mock = "mock" in str(source_bin).lower() or "mock" in str(output_root).lower()
    recording_source = (
        "synthetic-mock-ti-dca1000-import"
        if is_mock
        else "physical-ti-dca1000-import"
    )

    metadata = RecordingMetadata(
        recording_id=output_root.name,
        created_utc=datetime.now(timezone.utc).isoformat(),
        source=recording_source,
        radar_model=str(hardware["radar_model"]),
        firmware_version=str(hardware["firmware_version"]),
        sample_format="complex64-npy",
        sample_rate_hz=float(capture["sample_rate_hz"]),
        channels=raw_config.rx_channels,
        notes=(
            f"DCA1000 source SHA-256={_sha256(source_bin)}; "
            f"capture card={hardware['capture_card']}; "
            f"mmWave Studio={hardware['mmwave_studio_version']}; "
            f"SDK={hardware['mmwave_sdk_version']}"
        ),
    )
    writer = RecordingWriter(output_root, metadata)

    codebook = ChallengeCodebook(
        start_frequency_offsets_hz=tuple(
            float(x) * 1e6 for x in challenge_cfg["start_frequency_offsets_mhz"]
        ),
        chirp_slopes_hz_per_s=tuple(
            (float(rf["frequency_slope_mhz_per_us"]) + float(x)) * 1e12
            for x in challenge_cfg["slope_offsets_mhz_per_us"]
        ),
        chirp_permutations=tuple(
            tuple(int(v) for v in item)
            for item in challenge_cfg["chirp_permutations"]
        ),
    )
    anchor_id = str(hardware["anchor_id"])
    anchor_key = bytes.fromhex(anchor_key_hex)

    gt_state = GroundTruthState(
        position_m=tuple(float(x) for x in gt["target_position_m"]),
        velocity_mps=tuple(float(x) for x in gt["target_velocity_mps"]),
    )
    period_ns = int(float(rf["frame_periodicity_ms"]) * 1e6)

    sanity = []
    for raw_frame in reader.frames():
        epoch = raw_frame.frame_index
        challenge = derive_challenge(
            key=anchor_key,
            anchor_id=anchor_id,
            epoch=epoch,
            codebook=codebook,
        )
        writer.append(
            frame_id=f"{anchor_id}-e{epoch:06d}",
            anchor_id=anchor_id,
            epoch=epoch,
            timestamp_ns=epoch * period_ns,
            challenge=challenge,
            samples=raw_frame.samples,
            ground_truth=gt_state,
        )

        if epoch < 10:
            observation = estimate_ti_observation(
                raw_frame.samples,
                sample_rate_hz=float(rf["adc_sample_rate_ksps"]) * 1e3,
                frequency_slope_hz_per_s=float(
                    rf["frequency_slope_mhz_per_us"]
                )
                * 1e12,
                carrier_frequency_hz=float(rf["start_frequency_ghz"]) * 1e9,
                chirp_period_s=(
                    float(rf["idle_time_us"]) + float(rf["ramp_end_time_us"])
                )
                * 1e-6,
            )
            sanity.append(observation.model_dump(mode="json"))

    manifest = {
        "profile": str(profile_path),
        "profile_sha256": _sha256(profile_path),
        "source_bin": str(source_bin),
        "source_bin_sha256": _sha256(source_bin),
        "output_recording": str(output_root),
        "frame_count": frame_count,
        "bytes_per_frame": raw_config.bytes_per_frame,
        "raw_layout": raw_config.model_dump(mode="json"),
        "sanity_observations_first_10": sanity,
        "paper_eligibility": (
            "Physical source is necessary but not sufficient. The challenge "
            "schedule must be shown to match the waveform actually transmitted, "
            "and ground truth and ethics/protocol requirements must be satisfied."
        ),
    }
    (output_root / "acquisition_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
