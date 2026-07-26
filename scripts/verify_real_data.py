from __future__ import annotations

import argparse
import json
from pathlib import Path

from mosaic.real_data import verify_real_capture_pair


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the physical IWR6843ISK-ODS/DCA1000EVM target/background "
            "capture pair and reproduce the range-spectrum results."
        )
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("configs/ti_iwr6843isk_ods_real_capture.yaml"),
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("artifacts/runs/real-data-verification.json"),
    )
    parser.add_argument(
        "--output-spectrum",
        type=Path,
        default=Path("artifacts/runs/real-data-range-spectrum.csv"),
    )
    args = parser.parse_args()
    report = verify_real_capture_pair(
        profile_path=args.profile,
        output_report=args.output_report,
        output_spectrum_csv=args.output_spectrum,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["overall_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
