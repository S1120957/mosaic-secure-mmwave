import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import yaml

from mosaic.challenge import ChallengeCodebook
from mosaic.decision import decide_epoch
from mosaic.models import AnchorConfig
from mosaic.simulator import genuine_epoch, inconsistent_phantom_epoch
from mosaic.transparency import AppendOnlyLog, merkle_root_hex
from mosaic.recording import validate_recording
from mosaic.recorded_pipeline import replay_recording

def run_demo(config_path: Path) -> int:
    cfg = yaml.safe_load(config_path.read_text())
    anchors = {}
    keys = {}
    for item in cfg["anchors"]:
        a = AnchorConfig(anchor_id=item["id"],
                         position_m=tuple(item["position_m"]),
                         key_hex=item["key_hex"])
        anchors[a.anchor_id] = a
        keys[a.anchor_id] = bytes.fromhex(a.key_hex)

    cb = ChallengeCodebook(
        tuple(cfg["challenge"]["start_frequency_offsets_hz"]),
        tuple(cfg["challenge"]["chirp_slopes_hz_per_s"]),
        tuple(tuple(x) for x in cfg["challenge"]["chirp_permutations"]))
    rng = np.random.default_rng(cfg["seed"])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path("artifacts/runs") / f"synthetic-{run_id}"
    outdir.mkdir(parents=True, exist_ok=True)
    log = AppendOnlyLog(outdir/"transparency.jsonl")

    position = np.asarray(cfg["scenario"]["initial_position_m"], float)
    velocity = np.asarray(cfg["scenario"]["velocity_mps"], float)
    counts = {"verified": 0, "uncertain": 0, "unavailable": 0}

    with (outdir/"decisions.jsonl").open("w") as df:
        for epoch in range(cfg["epochs"]):
            common = dict(
                rng=rng, epoch=epoch, position=tuple(position),
                velocity=tuple(velocity), anchors=anchors, keys=keys,
                codebook=cb,
                range_std=cfg["measurement"]["range_std_m"],
                velocity_std=cfg["measurement"]["radial_velocity_std_mps"],
                bearing_std=cfg["measurement"]["bearing_std_rad"])
            if epoch < cfg["scenario"]["phantom_start_epoch"]:
                evidence = genuine_epoch(**common)
                position += velocity*cfg["dt_seconds"]
            else:
                common["position"] = tuple(cfg["scenario"]["phantom_position_m"])
                common["velocity"] = (0.0, 0.0)
                evidence = inconsistent_phantom_epoch(**common)

            result = decide_epoch(
                epoch=epoch, evidence=evidence, anchors=anchors, keys=keys,
                quorum_l=cfg["decision"]["quorum_l"],
                binding_threshold=cfg["decision"]["binding_threshold"],
                geometry_threshold=cfg["decision"]["geometry_threshold"],
                verified_cost_threshold=cfg["decision"]["verified_cost_threshold"],
                uncertainty_margin=cfg["decision"]["uncertainty_margin"])
            counts[result.decision.value] += 1
            df.write(result.model_dump_json()+"\n")
            records = [e.model_dump_json().encode() for e in evidence]
            log.append({"epoch": epoch,
                        "decision": result.model_dump(mode="json"),
                        "evidence_merkle_root": merkle_root_hex(records)})

    summary = {"output_dir": str(outdir), "counts": counts,
               "log_valid": log.verify(),
               "challenge_cardinality": cb.cardinality}
    (outdir/"summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0

def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("synthetic-demo")
    d.add_argument("--config", type=Path, default=Path("configs/synthetic.yaml"))

    v = sub.add_parser("validate-recording")
    v.add_argument("recording", type=Path)

    r = sub.add_parser("replay-recording")
    r.add_argument("recording", type=Path)
    r.add_argument("--config", type=Path, default=Path("configs/synthetic.yaml"))

    args = p.parse_args()
    if args.cmd == "synthetic-demo":
        return run_demo(args.config)
    if args.cmd == "validate-recording":
        print(json.dumps(validate_recording(args.recording), indent=2))
        return 0
    if args.cmd == "replay-recording":
        cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        anchors, keys = {}, {}
        for item in cfg["anchors"]:
            a = AnchorConfig(anchor_id=item["id"],
                             position_m=tuple(item["position_m"]),
                             key_hex=item["key_hex"])
            anchors[a.anchor_id] = a
            keys[a.anchor_id] = bytes.fromhex(a.key_hex)
        results = replay_recording(
            recording_root=args.recording,
            anchors=anchors,
            keys=keys,
            quorum_l=cfg["decision"]["quorum_l"],
            binding_threshold=cfg["decision"]["binding_threshold"],
            geometry_threshold=cfg["decision"]["geometry_threshold"],
            verified_cost_threshold=cfg["decision"]["verified_cost_threshold"],
            uncertainty_margin=cfg["decision"]["uncertainty_margin"])
        print(json.dumps([x.model_dump(mode="json") for x in results], indent=2))
        return 0
    raise RuntimeError(args.cmd)

if __name__ == "__main__":
    raise SystemExit(main())
