from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from mosaic.calibration import load_calibration_artifact
from mosaic.frozen_pipeline import replay_with_frozen_calibration
from mosaic.models import AnchorConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/synthetic.yaml")
    )
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
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

    calibration = load_calibration_artifact(args.calibration)
    results = replay_with_frozen_calibration(
        recording_root=args.recording,
        calibration=calibration,
        anchors=anchors,
        keys=keys,
    )
    counts = {"verified": 0, "uncertain": 0, "unavailable": 0}
    for result in results:
        counts[result.decision.value] += 1
    print(
        json.dumps(
            {
                "recording": str(args.recording),
                "calibration": str(args.calibration),
                "epochs": len(results),
                "counts": counts,
                "eligible_for_paper_results": (
                    calibration.provenance.eligible_for_paper_results
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
