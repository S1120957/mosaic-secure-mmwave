from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from mosaic.evidence import create_evidence
from mosaic.feasibility import solve_one_target
from mosaic.geometry import geometry_score, predict
from mosaic.models import AnchorConfig, Observation
from mosaic.recording import RecordingReader, sha256_file
from mosaic.signal_processing import (
    estimate_proxy_binding_statistic,
    estimate_proxy_observation,
)


CALIBRATION_SCHEMA_VERSION = "1.0"
CALIBRATION_ALGORITHM_VERSION = "phase-b-1.0"


class MeasurementCalibration(BaseModel):
    model_config = ConfigDict(frozen=True)

    range_std_m: float = Field(gt=0)
    radial_velocity_std_mps: float = Field(gt=0)
    bearing_std_rad: float = Field(gt=0)
    range_bias_m: float
    radial_velocity_bias_mps: float
    bearing_bias_rad: float
    sample_count: int = Field(gt=0)


class ThresholdCalibration(BaseModel):
    model_config = ConfigDict(frozen=True)

    binding_threshold: float = Field(ge=0, le=1)
    geometry_threshold: float = Field(ge=0)
    verified_cost_threshold: float = Field(ge=0)
    uncertainty_margin: float = Field(ge=0)
    target_benign_false_rejection_rate: float = Field(gt=0, lt=1)
    binding_quantile: float = Field(gt=0, lt=1)
    geometry_quantile: float = Field(gt=0, lt=1)
    feasibility_quantile: float = Field(gt=0, lt=1)
    uncertainty_quantile: float = Field(gt=0, lt=1)


class CalibrationProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = CALIBRATION_SCHEMA_VERSION
    algorithm_version: str = CALIBRATION_ALGORITHM_VERSION
    created_utc: str
    recording_id: str
    recording_source: str
    recording_metadata_sha256: str
    recording_frames_sha256: str
    configuration_sha256: str
    benign_only: bool = True
    eligible_for_paper_results: bool
    eligibility_reason: str
    epoch_count: int = Field(gt=0)
    anchor_ids: tuple[str, ...]
    quorum_l: int = Field(gt=0)
    random_seed: int


class CalibrationArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    provenance: CalibrationProvenance
    measurements_by_anchor: dict[str, MeasurementCalibration]
    pooled_measurement: MeasurementCalibration
    thresholds: ThresholdCalibration
    empirical_benign_rates: dict[str, float]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class CalibrationOptions:
    quorum_l: int
    target_benign_false_rejection_rate: float = 0.05
    binding_lower_quantile: float = 0.01
    geometry_lower_quantile: float = 0.01
    feasibility_upper_quantile: float = 0.95
    uncertainty_upper_quantile: float = 0.995
    std_floor_range_m: float = 0.02
    std_floor_velocity_mps: float = 0.03
    std_floor_bearing_rad: float = 0.01
    random_seed: int = 2027


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _robust_location_scale(values: Sequence[float], floor: float) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        raise ValueError("Cannot calibrate an empty residual sequence")
    median = float(np.median(x))
    mad = float(np.median(np.abs(x - median)))
    robust_std = max(floor, 1.4826 * mad)
    return median, robust_std


def _wrapped_angle_difference(x: float, y: float) -> float:
    return float((x - y + math.pi) % (2 * math.pi) - math.pi)


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a quantile from no values")
    return float(np.quantile(np.asarray(values, dtype=float), q, method="higher"))


def _recording_file_hashes(root: Path) -> tuple[str, str]:
    return sha256_file(root / "metadata.json"), sha256_file(root / "frames.jsonl")


def _config_hash(
    anchors: Mapping[str, AnchorConfig],
    options: CalibrationOptions,
) -> str:
    payload = {
        "anchors": {
            anchor_id: {
                "position_m": list(anchor.position_m),
            }
            for anchor_id, anchor in sorted(anchors.items())
        },
        "options": options.__dict__,
    }
    return _sha256_json(payload)


def _eligible_for_paper(source: str, radar_model: str) -> tuple[bool, str]:
    source_lower = source.lower()
    radar_lower = radar_model.lower()
    if "synthetic" in source_lower or "proxy" in radar_lower or "sim" in radar_lower:
        return (
            False,
            "Synthetic/proxy recordings validate software only and are not eligible "
            "for manuscript performance claims.",
        )
    return (
        True,
        "Recording metadata does not identify the source as synthetic or proxy. "
        "Human-subject, hardware, and protocol eligibility must still be reviewed.",
    )


def calibrate_recording(
    *,
    recording_root: Path,
    anchors: Mapping[str, AnchorConfig],
    keys: Mapping[str, bytes],
    options: CalibrationOptions,
) -> CalibrationArtifact:
    reader = RecordingReader(recording_root, verify_hashes=True)
    indexes = list(reader.indexes())
    if not indexes:
        raise ValueError("Recording contains no frames")

    frames = list(reader.frames())
    ground_truth_by_epoch: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
    residuals_by_anchor: dict[str, dict[str, list[float]]] = {}
    binding_scores: list[float] = []
    geometry_scores: list[float] = []
    frame_rows: list[dict[str, Any]] = []

    for loaded in frames:
        idx = loaded.index
        if idx.anchor_id not in anchors:
            continue
        if idx.ground_truth is None:
            raise ValueError(
                f"Frame {idx.frame_id} has no ground_truth; benign calibration requires "
                "position and velocity ground truth."
            )

        gt_position = idx.ground_truth.position_m
        gt_velocity = idx.ground_truth.velocity_mps
        prior = ground_truth_by_epoch.get(idx.epoch)
        current = (gt_position, gt_velocity)
        if prior is not None and prior != current:
            raise ValueError(f"Inconsistent ground truth in epoch {idx.epoch}")
        ground_truth_by_epoch[idx.epoch] = current

        estimated = estimate_proxy_observation(loaded.samples)
        expected = predict(
            anchors[idx.anchor_id].position_m,
            gt_position,
            gt_velocity,
        )
        r_expected, v_expected, theta_expected = expected

        bucket = residuals_by_anchor.setdefault(
            idx.anchor_id,
            {"range": [], "velocity": [], "bearing": []},
        )
        bucket["range"].append(estimated.range_m - r_expected)
        bucket["velocity"].append(
            estimated.radial_velocity_mps - v_expected
        )
        bucket["bearing"].append(
            _wrapped_angle_difference(estimated.bearing_rad, theta_expected)
        )

        binding = estimate_proxy_binding_statistic(
            loaded.samples,
            challenge=idx.challenge,
        )
        binding_scores.append(binding)
        frame_rows.append(
            {
                "index": idx,
                "samples": loaded.samples,
                "estimated": estimated,
                "binding": binding,
            }
        )

    if len(ground_truth_by_epoch) < 2:
        raise ValueError("Calibration requires at least two benign epochs")

    measurements_by_anchor: dict[str, MeasurementCalibration] = {}
    pooled = {"range": [], "velocity": [], "bearing": []}
    for anchor_id, bucket in sorted(residuals_by_anchor.items()):
        for key in pooled:
            pooled[key].extend(bucket[key])
        range_bias, range_std = _robust_location_scale(
            bucket["range"], options.std_floor_range_m
        )
        velocity_bias, velocity_std = _robust_location_scale(
            bucket["velocity"], options.std_floor_velocity_mps
        )
        bearing_bias, bearing_std = _robust_location_scale(
            bucket["bearing"], options.std_floor_bearing_rad
        )
        measurements_by_anchor[anchor_id] = MeasurementCalibration(
            range_std_m=range_std,
            radial_velocity_std_mps=velocity_std,
            bearing_std_rad=bearing_std,
            range_bias_m=range_bias,
            radial_velocity_bias_mps=velocity_bias,
            bearing_bias_rad=bearing_bias,
            sample_count=len(bucket["range"]),
        )

    pooled_range_bias, pooled_range_std = _robust_location_scale(
        pooled["range"], options.std_floor_range_m
    )
    pooled_velocity_bias, pooled_velocity_std = _robust_location_scale(
        pooled["velocity"], options.std_floor_velocity_mps
    )
    pooled_bearing_bias, pooled_bearing_std = _robust_location_scale(
        pooled["bearing"], options.std_floor_bearing_rad
    )
    pooled_measurement = MeasurementCalibration(
        range_std_m=pooled_range_std,
        radial_velocity_std_mps=pooled_velocity_std,
        bearing_std_rad=pooled_bearing_std,
        range_bias_m=pooled_range_bias,
        radial_velocity_bias_mps=pooled_velocity_bias,
        bearing_bias_rad=pooled_bearing_bias,
        sample_count=len(pooled["range"]),
    )

    anchor_ids = tuple(sorted(residuals_by_anchor))
    if options.quorum_l > len(anchor_ids):
        raise ValueError("quorum_l exceeds the number of calibrated anchors")

    for epoch, (position, _) in sorted(ground_truth_by_epoch.items()):
        present = sorted(
            {
                row["index"].anchor_id
                for row in frame_rows
                if row["index"].epoch == epoch
            }
        )
        for subset in itertools.combinations(present, options.quorum_l):
            geometry_scores.append(
                geometry_score(
                    [anchors[anchor_id].position_m for anchor_id in subset],
                    position,
                )
            )

    binding_threshold = _quantile(
        binding_scores, options.binding_lower_quantile
    )
    geometry_threshold = _quantile(
        geometry_scores, options.geometry_lower_quantile
    )

    evidence_by_epoch: dict[int, list] = {}
    for row in frame_rows:
        idx = row["index"]
        m = measurements_by_anchor[idx.anchor_id]
        raw = row["estimated"]
        calibrated_observation = Observation(
            range_m=max(0.001, raw.range_m - m.range_bias_m),
            radial_velocity_mps=(
                raw.radial_velocity_mps - m.radial_velocity_bias_mps
            ),
            bearing_rad=_wrapped_angle_difference(
                raw.bearing_rad, m.bearing_bias_rad
            ),
            range_std_m=m.range_std_m,
            radial_velocity_std_mps=m.radial_velocity_std_mps,
            bearing_std_rad=m.bearing_std_rad,
        )
        evidence = create_evidence(
            key=keys[idx.anchor_id],
            anchor_id=idx.anchor_id,
            epoch=idx.epoch,
            challenge=idx.challenge,
            observation=calibrated_observation,
            binding_statistic=row["binding"],
            quality=1.0,
            sample_buffer=row["samples"].tobytes(order="C"),
        )
        evidence_by_epoch.setdefault(idx.epoch, []).append(evidence)

    feasibility_costs: list[float] = []
    insufficient_quorum = 0
    low_geometry = 0
    for epoch, epoch_evidence in sorted(evidence_by_epoch.items()):
        admitted = [
            item
            for item in epoch_evidence
            if item.binding_statistic >= binding_threshold
        ]
        if len(admitted) < options.quorum_l:
            insufficient_quorum += 1
            continue

        gt_position = ground_truth_by_epoch[epoch][0]
        best_cost: float | None = None
        found_diverse = False
        for subset in itertools.combinations(admitted, options.quorum_l):
            g = geometry_score(
                [anchors[e.anchor_id].position_m for e in subset],
                gt_position,
            )
            if g < geometry_threshold:
                continue
            found_diverse = True
            fit = solve_one_target(evidence=list(subset), anchors=anchors)
            if best_cost is None or fit.robust_cost < best_cost:
                best_cost = fit.robust_cost
        if not found_diverse or best_cost is None:
            low_geometry += 1
            continue
        feasibility_costs.append(best_cost)

    if not feasibility_costs:
        raise ValueError("No benign epoch produced a calibratable feasible quorum")

    gamma = _quantile(
        feasibility_costs, options.feasibility_upper_quantile
    )
    uncertain_upper = _quantile(
        feasibility_costs, options.uncertainty_upper_quantile
    )
    kappa = max(0.0, uncertain_upper - gamma)

    verified_count = sum(cost <= gamma for cost in feasibility_costs)
    uncertain_count = sum(
        gamma < cost <= gamma + kappa for cost in feasibility_costs
    )
    rejected_count = sum(cost > gamma + kappa for cost in feasibility_costs)
    total_epochs = len(ground_truth_by_epoch)

    eligible, reason = _eligible_for_paper(
        reader.metadata.source, reader.metadata.radar_model
    )
    metadata_hash, frames_hash = _recording_file_hashes(recording_root)

    artifact = CalibrationArtifact(
        provenance=CalibrationProvenance(
            created_utc=datetime.now(timezone.utc).isoformat(),
            recording_id=reader.metadata.recording_id,
            recording_source=reader.metadata.source,
            recording_metadata_sha256=metadata_hash,
            recording_frames_sha256=frames_hash,
            configuration_sha256=_config_hash(anchors, options),
            eligible_for_paper_results=eligible,
            eligibility_reason=reason,
            epoch_count=total_epochs,
            anchor_ids=anchor_ids,
            quorum_l=options.quorum_l,
            random_seed=options.random_seed,
        ),
        measurements_by_anchor=measurements_by_anchor,
        pooled_measurement=pooled_measurement,
        thresholds=ThresholdCalibration(
            binding_threshold=binding_threshold,
            geometry_threshold=geometry_threshold,
            verified_cost_threshold=gamma,
            uncertainty_margin=kappa,
            target_benign_false_rejection_rate=(
                options.target_benign_false_rejection_rate
            ),
            binding_quantile=options.binding_lower_quantile,
            geometry_quantile=options.geometry_lower_quantile,
            feasibility_quantile=options.feasibility_upper_quantile,
            uncertainty_quantile=options.uncertainty_upper_quantile,
        ),
        empirical_benign_rates={
            "verified": verified_count / total_epochs,
            "uncertain": uncertain_count / total_epochs,
            "rejected": rejected_count / total_epochs,
            "unavailable": insufficient_quorum / total_epochs,
            "low_geometry": low_geometry / total_epochs,
        },
        diagnostics={
            "binding_score_count": len(binding_scores),
            "binding_score_min": float(min(binding_scores)),
            "binding_score_median": float(np.median(binding_scores)),
            "binding_score_max": float(max(binding_scores)),
            "geometry_score_count": len(geometry_scores),
            "geometry_score_min": float(min(geometry_scores)),
            "geometry_score_median": float(np.median(geometry_scores)),
            "geometry_score_max": float(max(geometry_scores)),
            "feasibility_cost_count": len(feasibility_costs),
            "feasibility_cost_min": float(min(feasibility_costs)),
            "feasibility_cost_median": float(np.median(feasibility_costs)),
            "feasibility_cost_max": float(max(feasibility_costs)),
        },
    )
    return artifact


def write_calibration_artifact(
    artifact: CalibrationArtifact,
    output_path: Path,
) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = artifact.model_dump(mode="json")
    canonical = _canonical_json_bytes(payload)
    output_path.write_bytes(
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    digest = hashlib.sha256(canonical).hexdigest()
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(
        f"{digest}  {output_path.name}\n",
        encoding="utf-8",
    )
    return digest


def load_calibration_artifact(
    path: Path,
    *,
    verify_digest: bool = True,
) -> CalibrationArtifact:
    raw = json.loads(path.read_text(encoding="utf-8"))
    artifact = CalibrationArtifact.model_validate(raw)
    if verify_digest:
        digest_path = path.with_suffix(path.suffix + ".sha256")
        if not digest_path.exists():
            raise FileNotFoundError(f"Missing calibration digest: {digest_path}")
        expected = digest_path.read_text(encoding="utf-8").split()[0]
        actual = _sha256_json(artifact.model_dump(mode="json"))
        if actual != expected:
            raise ValueError(
                f"Calibration digest mismatch: expected {expected}, got {actual}"
            )
    return artifact


def verify_calibration_against_recording(
    *,
    artifact_path: Path,
    recording_root: Path,
) -> dict[str, Any]:
    artifact = load_calibration_artifact(artifact_path, verify_digest=True)
    metadata_hash, frames_hash = _recording_file_hashes(recording_root)
    metadata_match = (
        metadata_hash == artifact.provenance.recording_metadata_sha256
    )
    frames_match = frames_hash == artifact.provenance.recording_frames_sha256
    return {
        "valid": metadata_match and frames_match,
        "artifact": str(artifact_path),
        "recording": str(recording_root),
        "metadata_hash_match": metadata_match,
        "frames_hash_match": frames_match,
        "eligible_for_paper_results": (
            artifact.provenance.eligible_for_paper_results
        ),
        "eligibility_reason": artifact.provenance.eligibility_reason,
    }
