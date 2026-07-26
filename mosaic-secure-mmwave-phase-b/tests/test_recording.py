from datetime import datetime, timezone

import numpy as np

from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.recording import (
    RecordingFormatError,
    RecordingMetadata,
    RecordingReader,
    RecordingWriter,
    validate_recording,
)


def test_recording_round_trip_and_hash_check(tmp_path):
    key = bytes.fromhex("11" * 32)
    codebook = ChallengeCodebook((0.0,), (6e13,), ((0, 1),))
    challenge = derive_challenge(
        key=key, anchor_id="A1", epoch=0, codebook=codebook
    )
    root = tmp_path / "recording"
    writer = RecordingWriter(
        root,
        RecordingMetadata(
            recording_id="test",
            created_utc=datetime.now(timezone.utc).isoformat(),
            source="unit-test",
            sample_rate_hz=1e6,
            channels=2,
        ),
    )
    samples = np.arange(32, dtype=np.float32).reshape(4, 4, 2)
    writer.append(
        frame_id="A1-e000000",
        anchor_id="A1",
        epoch=0,
        timestamp_ns=0,
        challenge=challenge,
        samples=samples,
    )

    loaded = list(RecordingReader(root).frames())
    assert len(loaded) == 1
    assert np.array_equal(loaded[0].samples, samples)
    summary = validate_recording(root)
    assert summary["valid"]
    assert summary["frames"] == 1

    sample_path = root / loaded[0].index.sample_file
    tampered = np.load(sample_path)
    tampered[0, 0, 0] += 1
    np.save(sample_path, tampered, allow_pickle=False)

    try:
        list(RecordingReader(root).frames())
        assert False, "Expected hash mismatch"
    except RecordingFormatError:
        pass
