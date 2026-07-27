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
| data/emulated/gen4_target.bin | emulated | 3dd5b6ebfe642e338321f98cac4a8c0da1117234111abbc7a4f7389d4a05effe | generate_gen4_dataset.py; synthetic regression fixture; not paper-eligible |
| data/emulated/gen4_bg.bin | emulated | 1acebdf7bff2e8b8fb0db6ecbfe9adff68f8f2eb97e632c8f83e31a6d3b70453 | generate_gen4_dataset.py; synthetic regression fixture; not paper-eligible |

| data/real-data/iwr6843-dca1000-session01/adc_data.bin | emulated | 69c5eaa33e587ddbaf12ebbd6528f369d0dd9a12d9ca49ba763f7ccfb738de85 | legacy repository fixture; not paper-eligible |
| data/real-data/iwr6843-dca1000-session01/adc_data_bg.bin | emulated | ef25a581cfaa744423ecb7f18d827fb3032decb985e5e2f4dca9e00a73617ec6 | legacy repository fixture; not paper-eligible |
