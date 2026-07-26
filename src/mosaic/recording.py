from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from mosaic.models import Challenge, Evidence, Observation


class RecordingMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    recording_id: str
    created_utc: str
    source: str
    radar_model: str = "synthetic"
    firmware_version: str = "n/a"
    sample_format: str = "float32"
    sample_rate_hz: float = Field(gt=0)
    channels: int = Field(gt=0)
    notes: str = ""


class GroundTruthState(BaseModel):
    model_config = ConfigDict(frozen=True)

    position_m: tuple[float, float]
    velocity_mps: tuple[float, float]


class RecordedFrameIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame_id: str
    anchor_id: str
    epoch: int = Field(ge=0)
    timestamp_ns: int = Field(ge=0)
    challenge: Challenge
    sample_file: str
    sample_sha256: str
    evidence: Evidence | None = None
    ground_truth: GroundTruthState | None = None


@dataclass(frozen=True)
class LoadedFrame:
    index: RecordedFrameIndex
    samples: np.ndarray


class RecordingFormatError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RecordingWriter:
    """Writes an immutable directory-based recording.

    Layout:
      metadata.json
      frames.jsonl
      samples/<frame_id>.npy
    """

    def __init__(self, root: Path, metadata: RecordingMetadata) -> None:
        self.root = root
        self.samples_dir = root / "samples"
        self.frames_path = root / "frames.jsonl"
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"Recording directory is not empty: {root}")
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        (root / "metadata.json").write_text(
            metadata.model_dump_json(indent=2), encoding="utf-8"
        )

    def append(
        self,
        *,
        frame_id: str,
        anchor_id: str,
        epoch: int,
        timestamp_ns: int,
        challenge: Challenge,
        samples: np.ndarray,
        evidence: Evidence | None = None,
        ground_truth: GroundTruthState | None = None,
    ) -> RecordedFrameIndex:
        if samples.ndim not in (1, 2, 3):
            raise ValueError("samples must be a 1D, 2D, or 3D NumPy array")
        sample_path = self.samples_dir / f"{frame_id}.npy"
        if sample_path.exists():
            raise FileExistsError(f"Duplicate frame_id: {frame_id}")
        array = np.asarray(samples)
        if np.iscomplexobj(array):
            array = array.astype(np.complex64, copy=False)
        else:
            array = array.astype(np.float32, copy=False)
        np.save(sample_path, array, allow_pickle=False)
        item = RecordedFrameIndex(
            frame_id=frame_id,
            anchor_id=anchor_id,
            epoch=epoch,
            timestamp_ns=timestamp_ns,
            challenge=challenge,
            sample_file=str(sample_path.relative_to(self.root)).replace("\\", "/"),
            sample_sha256=sha256_file(sample_path),
            evidence=evidence,
            ground_truth=ground_truth,
        )
        with self.frames_path.open("a", encoding="utf-8") as handle:
            handle.write(item.model_dump_json() + "\n")
        return item


class RecordingReader:
    def __init__(self, root: Path, *, verify_hashes: bool = True) -> None:
        self.root = root
        self.verify_hashes = verify_hashes
        metadata_path = root / "metadata.json"
        frames_path = root / "frames.jsonl"
        if not metadata_path.exists() or not frames_path.exists():
            raise RecordingFormatError(
                "Recording must contain metadata.json and frames.jsonl"
            )
        self.metadata = RecordingMetadata.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        self.frames_path = frames_path

    def indexes(self) -> Iterator[RecordedFrameIndex]:
        seen_ids: set[str] = set()
        for line_number, raw in enumerate(
            self.frames_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw.strip():
                continue
            try:
                item = RecordedFrameIndex.model_validate_json(raw)
            except Exception as exc:
                raise RecordingFormatError(
                    f"Invalid frame index at line {line_number}: {exc}"
                ) from exc
            if item.frame_id in seen_ids:
                raise RecordingFormatError(f"Duplicate frame_id: {item.frame_id}")
            seen_ids.add(item.frame_id)
            yield item

    def frames(self) -> Iterator[LoadedFrame]:
        for item in self.indexes():
            sample_path = self.root / item.sample_file
            if not sample_path.exists():
                raise RecordingFormatError(f"Missing sample file: {sample_path}")
            if self.verify_hashes:
                actual = sha256_file(sample_path)
                if actual != item.sample_sha256:
                    raise RecordingFormatError(
                        f"Hash mismatch for {item.frame_id}: {actual} != {item.sample_sha256}"
                    )
            samples = np.load(sample_path, allow_pickle=False)
            yield LoadedFrame(index=item, samples=samples)

    def summary(self) -> dict:
        indexes = list(self.indexes())
        anchors = sorted({x.anchor_id for x in indexes})
        epochs = sorted({x.epoch for x in indexes})
        with_evidence = sum(x.evidence is not None for x in indexes)
        return {
            "recording_id": self.metadata.recording_id,
            "source": self.metadata.source,
            "radar_model": self.metadata.radar_model,
            "frames": len(indexes),
            "anchors": anchors,
            "epochs": len(epochs),
            "epoch_min": min(epochs) if epochs else None,
            "epoch_max": max(epochs) if epochs else None,
            "frames_with_evidence": with_evidence,
        }


def validate_recording(root: Path) -> dict:
    reader = RecordingReader(root, verify_hashes=True)
    shapes: dict[str, int] = {}
    sample_count = 0
    for loaded in reader.frames():
        key = "x".join(str(x) for x in loaded.samples.shape)
        shapes[key] = shapes.get(key, 0) + 1
        sample_count += int(loaded.samples.size)
    result = reader.summary()
    result.update(
        {
            "valid": True,
            "sample_shapes": shapes,
            "total_scalar_samples": sample_count,
        }
    )
    return result
