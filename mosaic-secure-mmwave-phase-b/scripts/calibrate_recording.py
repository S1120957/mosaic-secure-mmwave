from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from mosaic.calibration import (
    CalibrationOptions,
    calibrate_recording,
    write_calibration_artifact,
)
from mosaic.models import AnchorConfig


def _load_anchors(config_path: Path):
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    anchors = {}
    keys = {}
    for item in cfg["anchors"]:
        anchor = AnchorConfig(
            anchor_id=item["id"],
            position_m=tuple(item["position_m"]),
            key_hex=item["key_hex"],
        )
        anchors[anchor.anchor_id] = anchor
        keys[anchor.anchor_id] = bytes.fromhex(anchor.key_hex)
    return cfg, anchors, keys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/synthetic.yaml")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/calibration/frozen-calibration.json"),
    )
    parser.add_argument("--quorum", type=int)
    parser.add_argument("--benign-frr", type=float, default=0.05)
    args = parser.parse_args()

    cfg, anchors, keys = _load_anchors(args.config)
    quorum = args.quorum or int(cfg["decision"]["quorum_l"])
    artifact = calibrate_recording(
        recording_root=args.recording,
        anchors=anchors,
        keys=keys,
        options=CalibrationOptions(
            quorum_l=quorum,
            target_benign_false_rejection_rate=args.benign_frr,
            feasibility_upper_quantile=1.0 - args.benign_frr,
        ),
    )
    digest = write_calibration_artifact(artifact, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": digest,
                "eligible_for_paper_results": (
                    artifact.provenance.eligible_for_paper_results
                ),
                "eligibility_reason": artifact.provenance.eligibility_reason,
                "thresholds": artifact.thresholds.model_dump(mode="json"),
                "empirical_benign_rates": artifact.empirical_benign_rates,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
