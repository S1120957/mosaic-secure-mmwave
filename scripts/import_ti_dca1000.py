from __future__ import annotations

import argparse
import json
from pathlib import Path

from mosaic.ti_capture import import_dca1000_recording


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("configs/ti_iwr6843isk_ods_single_anchor.yaml"),
    )
    parser.add_argument("--source-bin", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--anchor-key-hex",
        required=True,
        help="64 hexadecimal characters; use a research key, never commit it.",
    )
    args = parser.parse_args()

    manifest = import_dca1000_recording(
        profile_path=args.profile,
        source_bin=args.source_bin,
        output_root=args.output,
        anchor_key_hex=args.anchor_key_hex,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
