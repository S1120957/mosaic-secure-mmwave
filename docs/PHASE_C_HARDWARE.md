# Phase C: TI IWR6843ISK-ODS + DCA1000EVM

## Selected reference stack

- Anchor: Texas Instruments IWR6843ISK-ODS
- Capture: Texas Instruments DCA1000EVM
- Host: Windows PC with dedicated 1-GbE interface
- Acquisition: mmWave Studio / DCA1000 CLI
- Initial scope: one static anchor and one surveyed stationary reflector/person

## Why this stack

The IWR6843 family operates from 60 to 64 GHz, supports four RX and three TX
channels, and exposes a high-speed ADC output. The ODS board provides wide
azimuth/elevation coverage and directly interfaces with DCA1000. DCA1000
captures LVDS output and streams it through 1-GbE.

## Purchase quantity for Phase C

Minimum:

- 1 x IWR6843ISK-ODS
- 1 x DCA1000EVM
- required interface cable supplied/confirmed for the selected board
- stable power supplies and USB cables
- Ethernet cable and host Ethernet adapter
- rigid tripod or mount
- tape measure or laser distance meter

Do not purchase three DCA1000 cards yet. First validate one complete raw-data
path, waveform reconfiguration, and file interpretation.

## Pre-capture checklist

1. Record board revision and serial number.
2. Install the TI tools appropriate for IWR6843.
3. Confirm DCA1000 Ethernet configuration and packet capture.
4. Run a no-target/background capture.
5. Place one stationary target at a surveyed range.
6. Capture at least 100 frames under one fixed radar profile.
7. Repeat for every proposed challenge profile.
8. Record the exact radar configuration exported by TI software.
9. Preserve the original `.bin` file read-only.
10. Compute SHA-256 before importing into MOSAIC.

## Critical challenge limitation

Phase C does not yet prove that start frequency, slope, or chirp permutation can
be changed independently at every MOSAIC epoch with sufficiently low overhead.
The selected TI firmware path must demonstrate this. Until then, the codebook
in `configs/ti_iwr6843isk_ods_single_anchor.yaml` is a proposed experiment
configuration, not an implemented security mechanism.

## First real recording protocol

- Room: uncluttered laboratory.
- Anchor height: record exactly.
- Target: static corner reflector first; human participant only after basic
  calibration and required approval.
- Ranges: 1, 2, 3, and 4 m, with at least three lateral bearings.
- Frames: at least 1,000 per position/profile for uncertainty estimation.
- Background: at least 1,000 frames without a target.
- Repetitions: power-cycle and repeat on at least three sessions.
- Output: one immutable recording directory per session/profile/location.

## Acceptance gate to Phase D

Proceed only after:

- raw file size matches the declared ADC layout;
- range peaks track surveyed target distances;
- repeated captures have stable hashes and manifests;
- configuration/profile identity is recorded for every capture;
- at least two distinct profiles can be captured and distinguished;
- the same-buffer evidence path is verified;
- no synthetic/proxy estimator values are reported as hardware performance.
