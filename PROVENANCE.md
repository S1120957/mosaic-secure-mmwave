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

| data/measured/challenge-feasibility/session02/profile_switch_bg_full.bin | emulated | 037a9d8cf302b5f1a9c65901c5fdea6a49cd8201106f3e48049682873c293824 | matches legacy Gen-4 emulated artifact; not paper-eligible |
| data/measured/challenge-feasibility/session02/profile_switch_target_full.bin | emulated | 5cb232274ab27aafac4b3b348a61310cacbb30babd19b672d32aa3a95ea8d534 | matches legacy Gen-4 emulated artifact; not paper-eligible |
| data/measured/challenge-feasibility/session03/profile_switch_bg_full.bin | measured | 5893803c417d7896e0002a3bd0b90248ef08120bee6aacb4313abc32103de5b1 | supplied as measured; acquisition provenance incomplete; not paper-eligible |
| data/measured/challenge-feasibility/session03/profile_switch_target_full.bin | measured | 3b303cb7f4fd339c70abfb44cf493c329de567051481f21ba208731e4ad739fc | supplied as measured; acquisition provenance incomplete; not paper-eligible |
