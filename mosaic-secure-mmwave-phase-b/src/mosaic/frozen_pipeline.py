from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mosaic.calibration import CalibrationArtifact
from mosaic.decision import decide_epoch
from mosaic.evidence import create_evidence
from mosaic.models import AnchorConfig, DecisionResult, Observation
from mosaic.recording import RecordingReader
from mosaic.signal_processing import (
    estimate_proxy_binding_statistic,
    estimate_proxy_observation,
)


def replay_with_frozen_calibration(
    *,
    recording_root: Path,
    calibration: CalibrationArtifact,
    anchors: dict[str, AnchorConfig],
    keys: dict[str, bytes],
) -> list[DecisionResult]:
    reader = RecordingReader(recording_root, verify_hashes=True)
    by_epoch = defaultdict(list)

    for loaded in reader.frames():
        idx = loaded.index
        if idx.anchor_id not in anchors or idx.anchor_id not in keys:
            continue
        if idx.anchor_id not in calibration.measurements_by_anchor:
            continue

        m = calibration.measurements_by_anchor[idx.anchor_id]
        raw = estimate_proxy_observation(loaded.samples)
        observation = Observation(
            range_m=max(0.001, raw.range_m - m.range_bias_m),
            radial_velocity_mps=(
                raw.radial_velocity_mps - m.radial_velocity_bias_mps
            ),
            bearing_rad=raw.bearing_rad - m.bearing_bias_rad,
            range_std_m=m.range_std_m,
            radial_velocity_std_mps=m.radial_velocity_std_mps,
            bearing_std_rad=m.bearing_std_rad,
        )
        binding = estimate_proxy_binding_statistic(
            loaded.samples,
            challenge=idx.challenge,
        )
        evidence = create_evidence(
            key=keys[idx.anchor_id],
            anchor_id=idx.anchor_id,
            epoch=idx.epoch,
            challenge=idx.challenge,
            observation=observation,
            binding_statistic=binding,
            quality=1.0,
            sample_buffer=loaded.samples.tobytes(order="C"),
        )
        by_epoch[idx.epoch].append(evidence)

    t = calibration.thresholds
    results = []
    for epoch in sorted(by_epoch):
        results.append(
            decide_epoch(
                epoch=epoch,
                evidence=by_epoch[epoch],
                anchors=anchors,
                keys=keys,
                quorum_l=calibration.provenance.quorum_l,
                binding_threshold=t.binding_threshold,
                geometry_threshold=t.geometry_threshold,
                verified_cost_threshold=t.verified_cost_threshold,
                uncertainty_margin=t.uncertainty_margin,
            )
        )
    return results
