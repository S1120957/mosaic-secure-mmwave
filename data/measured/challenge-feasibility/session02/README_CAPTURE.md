# session02 capture instructions

This directory is a capture template. It is not measured evidence until the physical acquisition is completed.

Required files after capture:
- `profile_switch_target_full.bin`
- `profile_switch_bg_full.bin`
- `runtime_control_capture.log`
- `per_subframe_timestamps.json`
- `ground_truth.json`
- `provenance.json`
- `SHA256SUMS`

Acceptance requirements:
- exactly 2,000 subframes;
- exactly 1,000 P0 and 1,000 P1;
- exactly 65,536 bytes per subframe;
- exactly 131,072,000 bytes per binary;
- strictly alternating P0/P1 profile sequence;
- zero missing timestamp records;
- independent ground truth completed;
- hashes recomputed from captured binaries.
