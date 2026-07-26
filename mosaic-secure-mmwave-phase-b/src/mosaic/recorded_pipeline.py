from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mosaic.decision import decide_epoch
from mosaic.models import AnchorConfig, DecisionResult
from mosaic.recording import RecordingReader
from mosaic.signal_processing import estimate_proxy_observation
from mosaic.evidence import create_evidence


def replay_recording(
    *,
    recording_root: Path,
    anchors: dict[str, AnchorConfig],
    keys: dict[str, bytes],
    quorum_l: int,
    binding_threshold: float,
    geometry_threshold: float,
    verified_cost_threshold: float,
    uncertainty_margin: float,
) -> list[DecisionResult]:
    """Replay recorded frames through evidence creation and fusion.

    If a frame already contains evidence, it is used directly. Otherwise,
    proxy observations are estimated from the stored samples and signed.
    """
    reader = RecordingReader(recording_root, verify_hashes=True)
    by_epoch = defaultdict(list)

    for loaded in reader.frames():
        idx = loaded.index
        if idx.anchor_id not in anchors or idx.anchor_id not in keys:
            continue

        if idx.evidence is not None:
            evidence = idx.evidence
        else:
            observation = estimate_proxy_observation(loaded.samples)
            evidence = create_evidence(
                key=keys[idx.anchor_id],
                anchor_id=idx.anchor_id,
                epoch=idx.epoch,
                challenge=idx.challenge,
                observation=observation,
                binding_statistic=0.95,
                quality=0.90,
                sample_buffer=loaded.samples.tobytes(order="C"),
            )
        by_epoch[idx.epoch].append(evidence)

    results: list[DecisionResult] = []
    for epoch in sorted(by_epoch):
        results.append(
            decide_epoch(
                epoch=epoch,
                evidence=by_epoch[epoch],
                anchors=anchors,
                keys=keys,
                quorum_l=quorum_l,
                binding_threshold=binding_threshold,
                geometry_threshold=geometry_threshold,
                verified_cost_threshold=verified_cost_threshold,
                uncertainty_margin=uncertainty_margin,
            )
        )
    return results
