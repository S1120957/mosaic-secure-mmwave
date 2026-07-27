#!/usr/bin/env python3
"""Validate provenance for governed MOSAIC research artifacts."""

from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "PROVENANCE.md"

VALID_TAGS = {"emulated", "measured", "derived"}

# Only these locations require individual provenance registration.
GOVERNED_ROOTS = (
    ROOT / "data" / "emulated",
    ROOT / "data" / "measured",
    ROOT / "data" / "real-data",
)

# Local/generated areas that must never be scanned individually.
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "build",
    ".pytest_cache",
    ".venv",
    "venv",
}

EXCLUDED_PREFIXES = (
    "data/raw/mock-ti/",
    "data/recorded/",
    "data/synthetic/",
)

ARTIFACT_SUFFIXES = {".bin", ".npy"}


def load_registry() -> dict[str, dict[str, str]]:
    if not REGISTRY_PATH.exists():
        raise SystemExit("PROVENANCE.md missing")

    entries: dict[str, dict[str, str]] = {}

    for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue

        cells = [cell.strip() for cell in line.split("|")[1:-1]]

        if len(cells) < 3:
            continue

        artifact_path, tag, sha256 = cells[:3]

        if tag not in VALID_TAGS:
            continue

        entries[artifact_path] = {
            "tag": tag,
            "sha256": sha256.lower(),
        }

    return entries


def is_excluded(path: pathlib.Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True

    rel = path.relative_to(ROOT).as_posix()

    return any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def governed_artifacts() -> list[pathlib.Path]:
    artifacts: list[pathlib.Path] = []

    for governed_root in GOVERNED_ROOTS:
        if not governed_root.exists():
            continue

        for path in governed_root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in ARTIFACT_SUFFIXES:
                continue

            if is_excluded(path):
                continue

            artifacts.append(path)

    return sorted(artifacts)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def main() -> int:
    registry = load_registry()
    problems: list[str] = []

    artifacts = governed_artifacts()

    for path in artifacts:
        relative_path = path.relative_to(ROOT).as_posix()

        if relative_path not in registry:
            problems.append(f"UNTAGGED  {relative_path}")
            continue

        expected_hash = registry[relative_path]["sha256"]

        if not expected_hash or expected_hash == "(fill)":
            problems.append(f"MISSING HASH  {relative_path}")
            continue

        actual_hash = sha256_file(path)

        if actual_hash != expected_hash:
            problems.append(
                f"HASH MISMATCH  {relative_path}\n"
                f"  want {expected_hash}\n"
                f"  got  {actual_hash}"
            )

    for artifact_path in registry:
        absolute_path = ROOT / artifact_path

        if (
            artifact_path.endswith((".bin", ".npy"))
            and not absolute_path.exists()
        ):
            problems.append(f"REGISTERED BUT MISSING  {artifact_path}")

    for problem in problems:
        print(problem)

    print(
        f"\n{len(registry)} registered, "
        f"{len(artifacts)} governed artifact(s), "
        f"{len(problems)} problem(s)"
    )

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())