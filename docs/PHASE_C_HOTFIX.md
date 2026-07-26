# Phase-C hotfix

This patch fixes two issues found during the mock DCA1000 import:

1. `RecordingWriter` now preserves complex ADC arrays as `complex64` instead
   of casting them to `float32` and discarding the Q channel.
2. Imports whose source or output path contains `mock` are marked
   `synthetic-mock-ti-dca1000-import`, preventing accidental classification
   as physical data.

Delete and regenerate any MOSAIC recording produced before this patch from a
complex DCA1000 source. The original `.bin` remains authoritative.
