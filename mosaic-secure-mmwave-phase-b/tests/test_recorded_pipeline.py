from datetime import datetime, timezone

import numpy as np

from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.models import AnchorConfig
from mosaic.recorded_pipeline import replay_recording
from mosaic.recording import RecordingMetadata, RecordingWriter
from mosaic.geometry import predict
from mosaic.signal_processing import synthetic_fmcw_buffer


def test_recorded_replay_produces_epoch_decision(tmp_path):
    anchors = {
        "A1": AnchorConfig(anchor_id="A1", position_m=(0, 0), key_hex="11" * 32),
        "A2": AnchorConfig(anchor_id="A2", position_m=(5, 0), key_hex="22" * 32),
        "A3": AnchorConfig(anchor_id="A3", position_m=(2.5, 4), key_hex="33" * 32),
    }
    keys = {k: bytes.fromhex(v.key_hex) for k, v in anchors.items()}
    codebook = ChallengeCodebook((-2e7, 0, 2e7), (5.5e13, 6e13), ((0, 1), (1, 0)))

    root = tmp_path / "recording"
    writer = RecordingWriter(
        root,
        RecordingMetadata(
            recording_id="replay",
            created_utc=datetime.now(timezone.utc).isoformat(),
            source="unit-test",
            radar_model="proxy",
            sample_rate_hz=2e6,
            channels=4,
        ),
    )
    rng = np.random.default_rng(4)
    position = (2.0, 1.5)
    velocity = (0.2, 0.1)

    for aid, anchor in anchors.items():
        challenge = derive_challenge(
            key=keys[aid], anchor_id=aid, epoch=0, codebook=codebook
        )
        r, rv, bearing = predict(anchor.position_m, position, velocity)
        samples = synthetic_fmcw_buffer(
            range_m=r,
            radial_velocity_mps=rv,
            bearing_rad=bearing,
            rng=rng,
        )
        writer.append(
            frame_id=f"{aid}-e000000",
            anchor_id=aid,
            epoch=0,
            timestamp_ns=0,
            challenge=challenge,
            samples=samples,
        )

    results = replay_recording(
        recording_root=root,
        anchors=anchors,
        keys=keys,
        quorum_l=3,
        binding_threshold=0.8,
        geometry_threshold=0.05,
        verified_cost_threshold=100.0,
        uncertainty_margin=20.0,
    )
    assert len(results) == 1
    assert len(results[0].accepted_anchor_ids) == 3
