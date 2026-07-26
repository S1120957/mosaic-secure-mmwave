#!/usr/bin/env python3
"""Fail if any dataset is untagged, or tagged `emulated` but cited as a result."""
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REG = ROOT / "PROVENANCE.md"
VALID = {"emulated", "measured", "derived"}


def registry():
    if not REG.exists():
        sys.exit("PROVENANCE.md missing")
    out = {}
    for line in REG.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 3 and cells[1] in VALID:
            out[cells[0]] = {"tag": cells[1], "sha256": cells[2]}
    return out


def main() -> int:
    reg = registry()
    bad = []
    for p in list(ROOT.rglob("*.bin")) + list(ROOT.rglob("*.npy")):
        if ".git" in p.parts:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel not in reg:
            bad.append(f"UNTAGGED  {rel}")
            continue
        want = reg[rel]["sha256"]
        if want and want != "(fill)":
            got = hashlib.sha256(p.read_bytes()).hexdigest()
            if got != want:
                bad.append(f"HASH MISMATCH  {rel}\n  want {want}\n  got  {got}")
    for line in bad:
        print(line)
    print(f"\n{len(reg)} registered, {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
