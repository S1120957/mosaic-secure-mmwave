# Artifact provenance

Every dataset MUST appear here with exactly one tag.

| tag        | meaning                                              | paper-eligible |
|------------|------------------------------------------------------|----------------|
| `emulated` | synthesised from a documented signal model            | NO             |
| `measured` | captured from physical radar hardware                 | YES            |
| `derived`  | computed from a `measured` artifact                   | YES            |

Nothing tagged `emulated` may support a performance, security, or
deployment claim. `scripts/check_provenance.py` fails CI if an artifact
is untagged or if a figure/table cites an `emulated` artifact.

## Registry

| artifact | tag | sha256 | generator / session |
|----------|-----|--------|---------------------|
| data/emulated/gen4_target.bin | emulated | (fill) | generate_gen4_dataset.py |
| data/emulated/gen4_bg.bin     | emulated | (fill) | generate_gen4_dataset.py |

| data/real-data/iwr6843-dca1000-session01/adc_data.bin | emulated | 69c5eaa33e587ddbaf12ebbd6528f369d0dd9a12d9ca49ba763f7ccfb738de85 | legacy repository fixture; not paper-eligible |
| data/real-data/iwr6843-dca1000-session01/adc_data_bg.bin | emulated | ef25a581cfaa744423ecb7f18d827fb3032decb985e5e2f4dca9e00a73617ec6 | legacy repository fixture; not paper-eligible |
