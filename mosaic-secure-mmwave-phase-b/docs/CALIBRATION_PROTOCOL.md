# Phase B: benign calibration and threshold freezing

## Objective

Estimate all deployable uncertainty and decision thresholds using a benign
calibration recording only. Attack trials must not influence these values.

## Required inputs

Each calibration frame must contain:

- exact anchor identifier and epoch;
- exact per-anchor challenge;
- immutable sample file and SHA-256;
- synchronized ground-truth target position;
- synchronized ground-truth target velocity;
- anchor coordinates;
- no injected attack.

## Estimates

For every anchor, MOSAIC estimates robust median bias and MAD-based scale for:

- range;
- radial velocity;
- bearing.

The implementation uses floors to avoid zero or unrealistically small
uncertainty on synthetic or repeated data.

## Frozen thresholds

- `binding_threshold`: lower benign quantile of binding scores;
- `geometry_threshold`: lower benign quantile of L-anchor geometry scores;
- `verified_cost_threshold` (`Gamma`): upper benign feasibility quantile;
- `uncertainty_margin` (`kappa`): distance from Gamma to a stricter upper
  benign quantile.

The default target benign false-rejection rate is 5%, so Gamma is the 95th
percentile of benign feasibility cost. This is a protocol target, not a claim
until held-out benign evaluation is performed.

## Leakage prevention

1. Generate a dedicated benign calibration recording.
2. Freeze `frozen-calibration.json`.
3. Commit its SHA-256 and configuration.
4. Do not modify the artifact after viewing attack outcomes.
5. Evaluate all attacks and held-out benign runs with the frozen artifact.
6. Any recalibration starts a new experimental series and new artifact hash.

## Eligibility flag

Synthetic/proxy recordings are always marked:

```json
"eligible_for_paper_results": false
```

They validate the pipeline only. Hardware data require separate ethics,
protocol, calibration, and provenance review.
