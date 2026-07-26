# Hardware decisions before RF implementation

Resolve and measure each item before writing final implementation values:

| Item | Required record |
|---|---|
| Radar board | exact model, band, bandwidth, antenna configuration |
| Data interface | raw ADC or exact intermediate representation |
| Challenge controls | frequency, slope, phase, permutation support |
| Synchronization | mechanism and median/p95/worst-case error |
| Fusion host | CPU, RAM, OS, NIC, solver runtime |
| Ground truth | RGB-D, LiDAR, mocap, or tagged reference |
| A0 | passive/modulating reflector capability |
| A1 | active repeater and measured reaction latency |
| A2/A3 | emitter count, placement, common timing, response method |
| Power | external instrument and sample rate |
| Rooms | dimensions, materials, surveyed anchor coordinates |
| Human study | ethics, consent, safe fall protocol |

Recommended development order:
1. synthetic and recorded-data pipeline;
2. one real anchor adapter;
3. three-anchor synchronization;
4. benign multi-anchor fusion;
5. A0/A1 attacks;
6. A2/A3 coordinated attacks;
7. extended care-like deployment;
8. optional DLT comparison against a signed transparency log.
