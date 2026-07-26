# MOSAIC recorded-data format v1.0

Each recording is an immutable directory:

```text
recording-id/
├── metadata.json
├── frames.jsonl
└── samples/
    ├── A1-e000000.npy
    ├── A2-e000000.npy
    └── ...
```

## metadata.json

Records provenance and acquisition characteristics:

- schema version;
- recording identifier;
- UTC creation time;
- source;
- radar and firmware;
- sample format and sample rate;
- channel count;
- notes.

## frames.jsonl

One JSON object per anchor frame:

- `frame_id`;
- `anchor_id`;
- `epoch`;
- `timestamp_ns`;
- exact challenge;
- relative sample path;
- SHA-256 of the `.npy` file;
- optional precomputed signed evidence.

## Integrity rule

The `.npy` file hash is checked before replay. The same loaded array is used
for proxy observation extraction and evidence commitment. Hardware adapters
must preserve this same-buffer property.

## Scope

The included proxy FMCW generator and estimator validate software plumbing.
They are not a calibrated RF simulator and cannot support paper claims.


## Ground truth for calibration recordings

Calibration recordings add an optional `ground_truth` object to every frame:

```json
{
  "position_m": [2.1, 1.4],
  "velocity_mps": [0.2, 0.1]
}
```

It is mandatory for Phase-B calibration and must be consistent across all
anchors in an epoch.
