from datetime import datetime, timezone

import numpy as np

from mosaic.calibration import (
    CalibrationOptions,
    calibrate_recording,
    load_calibration_artifact,
    verify_calibration_against_recording,
    write_calibration_artifact,
)
from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.geometry import predict
from mosaic.models import AnchorConfig
from mosaic.recording import (
    GroundTruthState,
    RecordingMetadata,
    RecordingWriter,
)
from mosaic.signal_processing import synthetic_fmcw_buffer


def _make_recording(tmp_path, epochs=18):
    anchors = {
        "A1": AnchorConfig(anchor_id="A1", position_m=(0, 0), key_hex="11" * 32),
        "A2": AnchorConfig(anchor_id="A2", position_m=(5, 0), key_hex="22" * 32),
        "A3": AnchorConfig(anchor_id="A3", position_m=(2.5, 4), key_hex="33" * 32),
    }
    keys = {k: bytes.fromhex(v.key_hex) for k, v in anchors.items()}
    codebook = ChallengeCodebook(
        (-2e7, 0, 2e7), (5.5e13, 6e13), ((0, 1), (1, 0))
    )
    root = tmp_path / "calibration-recording"
    writer = RecordingWriter(
        root,
        RecordingMetadata(
            recording_id="synthetic-calibration",
            created_utc=datetime.now(timezone.utc).isoformat(),
            source="synthetic-benign-calibration",
            radar_model="proxy-fmcw",
            sample_rate_hz=2e6,
            channels=4,
        ),
    )
    rng = np.random.default_rng(8)
    position = np.array([1.2, 1.1], dtype=float)
    velocity = np.array([0.15, 0.08], dtype=float)

    for epoch in range(epochs):
        for aid, anchor in anchors.items():
            challenge = derive_challenge(
                key=keys[aid], anchor_id=aid, epoch=epoch, codebook=codebook
            )
            r, rv, bearing = predict(anchor.position_m, position, velocity)
            samples = synthetic_fmcw_buffer(
                range_m=r,
                radial_velocity_mps=rv,
                bearing_rad=bearing,
                rng=rng,
            )
            writer.append(
                frame_id=f"{aid}-e{epoch:06d}",
                anchor_id=aid,
                epoch=epoch,
                timestamp_ns=epoch * 100_000_000,
                challenge=challenge,
                samples=samples,
                ground_truth=GroundTruthState(
                    position_m=tuple(position),
                    velocity_mps=tuple(velocity),
                ),
            )
        position += velocity * 0.1
    return root, anchors, keys


def test_calibration_freeze_and_verify(tmp_path):
    root, anchors, keys = _make_recording(tmp_path)
    artifact = calibrate_recording(
        recording_root=root,
        anchors=anchors,
        keys=keys,
        options=CalibrationOptions(quorum_l=3),
    )
    assert artifact.thresholds.binding_threshold > 0
    assert artifact.thresholds.verified_cost_threshold >= 0
    assert artifact.provenance.benign_only
    assert not artifact.provenance.eligible_for_paper_results

    output = tmp_path / "frozen.json"
    write_calibration_artifact(artifact, output)
    loaded = load_calibration_artifact(output)
    assert loaded == artifact

    verification = verify_calibration_against_recording(
        artifact_path=output,
        recording_root=root,
    )
    assert verification["valid"]


def test_calibration_digest_detects_tampering(tmp_path):
    root, anchors, keys = _make_recording(tmp_path)
    artifact = calibrate_recording(
        recording_root=root,
        anchors=anchors,
        keys=keys,
        options=CalibrationOptions(quorum_l=3),
    )
    output = tmp_path / "frozen.json"
    write_calibration_artifact(artifact, output)

    text = output.read_text(encoding="utf-8")
    output.write_text(
        text.replace('"quorum_l": 3', '"quorum_l": 2'),
        encoding="utf-8",
    )
    try:
        load_calibration_artifact(output)
        assert False, "Expected digest mismatch"
    except ValueError:
        pass
