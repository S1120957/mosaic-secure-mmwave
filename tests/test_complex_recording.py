from datetime import datetime, timezone

import numpy as np

from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.recording import RecordingMetadata, RecordingReader, RecordingWriter


def test_recording_preserves_complex_iq(tmp_path):
    root = tmp_path / "complex-recording"
    writer = RecordingWriter(
        root,
        RecordingMetadata(
            recording_id="complex",
            created_utc=datetime.now(timezone.utc).isoformat(),
            source="unit-test",
            sample_format="complex64",
            sample_rate_hz=1e6,
            channels=2,
        ),
    )
    key = bytes.fromhex("11" * 32)
    challenge = derive_challenge(
        key=key,
        anchor_id="A1",
        epoch=0,
        codebook=ChallengeCodebook((0.0,), (6e13,), ((0, 1),)),
    )
    samples = (
        np.arange(32, dtype=np.float32).reshape(4, 4, 2)
        + 1j * np.arange(32, dtype=np.float32).reshape(4, 4, 2)[::-1]
    ).astype(np.complex64)

    writer.append(
        frame_id="A1-e000000",
        anchor_id="A1",
        epoch=0,
        timestamp_ns=0,
        challenge=challenge,
        samples=samples,
    )
    loaded = list(RecordingReader(root).frames())[0].samples
    assert loaded.dtype == np.complex64
    assert np.array_equal(loaded, samples)
