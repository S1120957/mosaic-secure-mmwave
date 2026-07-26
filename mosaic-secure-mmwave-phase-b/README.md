# MOSAIC: Challenge-Bound Multi-Anchor Attestation

Runnable pre-hardware research artifact for secure device-free mmWave sensing.

Implemented now:
- deterministic per-anchor challenge derivation;
- authenticated, epoch-bound evidence tuples;
- synthetic multi-anchor observations;
- geometry-diversity scoring;
- robust one-target feasibility;
- verified / uncertain / unavailable decisions;
- quorum-aware security-bound utilities;
- append-only transparency logging;
- tests and a reproducible synthetic demo.

Not yet claimed:
- real RF challenge soundness;
- physical phantom/vanish attacks;
- measured synchronization;
- energy, latency, or deployment results.

## Start

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
mosaic synthetic-demo --config configs/synthetic.yaml
```

Outputs are written to `artifacts/runs/`.

## Hardware boundary

The exact radar and timing platforms are intentionally abstracted behind
`RadarAnchorAdapter` and `TimingAdapter`. Final drivers must use the same
captured buffer for challenge binding and geometric estimation.

See `docs/HARDWARE_DECISIONS.md`.


## Phase A: synthetic and recorded-data pipeline

Generate an immutable recorded fixture:

```bash
python scripts/generate_recorded_fixture.py \
  --config configs/synthetic.yaml \
  --output data/recorded/synthetic-fixture \
  --epochs 12
```

Validate its schema, hashes, and sample files:

```bash
mosaic validate-recording data/recorded/synthetic-fixture
```

Replay recorded samples through proxy signal processing, evidence creation,
quorum checking, geometric diversity, and one-target feasibility:

```bash
mosaic replay-recording data/recorded/synthetic-fixture \
  --config configs/synthetic.yaml
```

The proxy signal processor is only for software validation. It must be replaced
by calibrated radar processing after hardware selection.


## Phase B: calibration and threshold freezing

Regenerate a benign fixture with ground truth:

```bash
rm -rf data/recorded/benign-calibration
python scripts/generate_recorded_fixture.py \
  --config configs/synthetic.yaml \
  --output data/recorded/benign-calibration \
  --epochs 200
```

Freeze calibration:

```bash
python scripts/calibrate_recording.py \
  data/recorded/benign-calibration \
  --config configs/synthetic.yaml \
  --output artifacts/calibration/frozen-calibration.json
```

Replay with the frozen artifact:

```bash
python scripts/replay_frozen.py \
  data/recorded/benign-calibration \
  artifacts/calibration/frozen-calibration.json \
  --config configs/synthetic.yaml
```

Synthetic artifacts are marked ineligible for paper performance claims.
