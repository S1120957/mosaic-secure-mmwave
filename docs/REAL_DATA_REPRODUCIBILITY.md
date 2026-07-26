# Physical IWR6843ISK-ODS + DCA1000EVM dataset

## Scope

This artifact contains a paired target/background ADC acquisition made with a
TI IWR6843ISK-ODS and DCA1000EVM. The repository preserves the supplied
binaries byte-for-byte and provides two independent processing paths:

1. the MOSAIC Python ingestion and verification path; and
2. a dependency-free C++17 range-spectrum validator.

## Dataset layout

```text
data/real-data/iwr6843-dca1000-session01/
├── adc_data.bin
├── adc_data_bg.bin
├── capture_metadata.json
├── ground_truth_manifest.json
├── radar_config.cfg
└── SHA256SUMS
```

The binary layout is:

```text
10 frames × 16 chirps × 4 RX × 256 ADC samples × 2 int16 components
```

The stored component order is `Q, I`, little-endian. The logical complex
sample is reconstructed as `I + jQ`. The storage traversal order is
`frame → chirp → RX → sample → component`. The canonical MOSAIC frame shape
after decoding is `[16, 256, 4]`.

## Reproduce with Python

```powershell
python scripts\verify_real_data.py `
  --profile configs\ti_iwr6843isk_ods_real_capture.yaml `
  --output-report artifacts\runs\real-data-verification.json `
  --output-spectrum artifacts\runs\real-data-range-spectrum.csv
```

The command checks both SHA-256 hashes, both file sizes, frame accounting,
Q/I decoding, the paired target-minus-background spectrum, and the surveyed
target bins.

## Reproduce independently with C++17

```powershell
cmake -S cpp -B build\cpp
cmake --build build\cpp --config Release

.\build\cpp\Release\validate_real_data.exe `
  data\real-data\iwr6843-dca1000-session01\adc_data.bin `
  data\real-data\iwr6843-dca1000-session01\adc_data_bg.bin
```

For single-configuration generators, the executable may appear directly
under `build\cpp` rather than `build\cpp\Release`.

## Expected physical range checks

- Primary target: bin 46, approximately 2.455 m, surveyed at 2.46 m.
- Secondary target: bin 13, approximately 0.694 m, surveyed at 0.68 m.

The exact bin spacing produced from the configured sample rate and slope is
approximately 0.053378 m/bin.

## Challenge-identity boundary

The physical files use one fixed radar profile. They validate physical
capture ingestion, binary provenance, Q/I interpretation, background
subtraction, and range recovery. They do not by themselves prove that MOSAIC
per-frame challenge rotation was transmitted. The report therefore marks
challenge-profile identity as `not_exercised_in_this_capture`.
