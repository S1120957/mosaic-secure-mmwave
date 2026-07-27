#!/usr/bin/env python3
"""
MOSAIC step-1 challenge-feasibility harness
===========================================

Two independent parts:

  PART A  size_codebook()      -- analytical, runs with NO hardware.
          Answers: for the IWR6843 + DCA1000 configuration you can actually
          program, how many DISTINGUISHABLE challenge states exist per
          component, and therefore what floor does beta_i >= 1/|C_i| impose
          on Theorem 6.7?

  PART B  analyse_captures()    -- needs the bench.
          Ingests N raw .bin captures, each with its .cfg and declared
          challenge setting, and emits the sensing-quality cost table that
          Sec. 4.2 promises via \\measure{}.

Usage
-----
    # today, no hardware:
    python mosaic_challenge_bench.py design

    # after capturing:
    python mosaic_challenge_bench.py analyse manifest.json

Capture manifest format (JSON):
    {
      "surveyed_range_m": 2.46,
      "surveyed_bearing_deg": 0.0,
      "layout": "dca1000",              # or "simple" for emulator output
      "captures": [
        {"label":"baseline",  "bin":"cap_base.bin", "cfg":"base.cfg",
         "challenge":{"df_khz":0,"slope_mhz_us":57.14,"perm":"identity"}},
        {"label":"slope+2",   "bin":"cap_s2.bin",   "cfg":"s2.cfg",
         "challenge":{"df_khz":0,"slope_mhz_us":59.14,"perm":"identity"}}
      ]
    }

Only numpy is required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

import numpy as np

C0 = 299_792_458.0  # m/s


# ======================================================================
# TI .cfg parsing
# ======================================================================

@dataclass
class RadarCfg:
    """Parameters recovered from a TI mmWave .cfg file."""
    start_freq_ghz: float = 60.0
    idle_time_us: float = 100.0
    adc_start_time_us: float = 6.0
    ramp_end_time_us: float = 60.0
    freq_slope_mhz_us: float = 60.0
    num_adc_samples: int = 256
    sample_rate_ksps: float = 5209.0
    num_rx: int = 4
    num_tx: int = 1
    chirp_start_idx: int = 0
    chirp_end_idx: int = 0
    num_loops: int = 16
    frame_period_ms: float = 33.33
    complex_adc: bool = True

    # ---- derived -----------------------------------------------------
    @property
    def adc_window_us(self) -> float:
        return 1000.0 * self.num_adc_samples / self.sample_rate_ksps

    @property
    def chirp_period_us(self) -> float:
        """Idle + ramp. THIS is the inter-chirp spacing for Doppler."""
        return self.idle_time_us + self.ramp_end_time_us

    @property
    def sweep_bandwidth_hz(self) -> float:
        return self.freq_slope_mhz_us * 1e12 * self.adc_window_us * 1e-6

    @property
    def range_res_m(self) -> float:
        return C0 / (2.0 * self.sweep_bandwidth_hz)

    @property
    def bin_hz(self) -> float:
        return self.sample_rate_ksps * 1e3 / self.num_adc_samples

    @property
    def chirps_per_frame(self) -> int:
        return (self.chirp_end_idx - self.chirp_start_idx + 1) * self.num_loops

    @property
    def wavelength_m(self) -> float:
        return C0 / (self.start_freq_ghz * 1e9)

    def range_to_bin(self, r_m: float) -> float:
        """Physical range -> fractional FFT bin (config-derived, not hardcoded)."""
        f_beat = 2.0 * r_m * self.freq_slope_mhz_us * 1e12 / C0
        return f_beat / self.bin_hz

    def bin_to_range(self, b: float) -> float:
        return b * self.bin_hz * C0 / (2.0 * self.freq_slope_mhz_us * 1e12)

    def summary(self) -> str:
        return (
            f"  start {self.start_freq_ghz} GHz | slope {self.freq_slope_mhz_us} MHz/us | "
            f"{self.num_adc_samples} samp @ {self.sample_rate_ksps} ksps\n"
            f"  ADC window {self.adc_window_us:.2f} us | sweep BW "
            f"{self.sweep_bandwidth_hz/1e9:.3f} GHz | range res "
            f"{self.range_res_m*100:.2f} cm\n"
            f"  chirp period (idle+ramp) {self.chirp_period_us:.2f} us | "
            f"{self.chirps_per_frame} chirps/frame | frame {self.frame_period_ms} ms"
        )


def parse_cfg(path: str) -> RadarCfg:
    """Parse the subset of a TI .cfg that determines the signal model."""
    cfg = RadarCfg()
    with open(path) as fh:
        for line in fh:
            line = line.split("%")[0].strip()
            if not line:
                continue
            tok = line.split()
            key, vals = tok[0], tok[1:]
            try:
                if key == "profileCfg" and len(vals) >= 11:
                    # profileId startFreq idleTime adcStartTime rampEndTime
                    # txOutPowerBackoff txPhaseShifter freqSlopeConst txStartTime
                    # numAdcSamples digOutSampleRate ...
                    cfg.start_freq_ghz = float(vals[1])
                    cfg.idle_time_us = float(vals[2])
                    cfg.adc_start_time_us = float(vals[3])
                    cfg.ramp_end_time_us = float(vals[4])
                    cfg.freq_slope_mhz_us = float(vals[7])
                    cfg.num_adc_samples = int(float(vals[9]))
                    cfg.sample_rate_ksps = float(vals[10])
                elif key == "frameCfg" and len(vals) >= 5:
                    cfg.chirp_start_idx = int(float(vals[0]))
                    cfg.chirp_end_idx = int(float(vals[1]))
                    cfg.num_loops = int(float(vals[2]))
                    cfg.frame_period_ms = float(vals[4])
                elif key == "channelCfg" and len(vals) >= 2:
                    cfg.num_rx = bin(int(float(vals[0]))).count("1")
                    cfg.num_tx = bin(int(float(vals[1]))).count("1")
                elif key == "adcCfg" and len(vals) >= 2:
                    cfg.complex_adc = int(float(vals[1])) in (1, 2)
            except (ValueError, IndexError):
                print(f"  [warn] could not parse: {line}", file=sys.stderr)
    return cfg


def sanity_check_cfg(cfg: RadarCfg) -> list[str]:
    """Catch the config defects that have already bitten this project."""
    problems = []
    need = cfg.adc_start_time_us + cfg.adc_window_us
    if cfg.ramp_end_time_us < need:
        problems.append(
            f"rampEndTime {cfg.ramp_end_time_us:.2f} us < adcStartTime + ADC window "
            f"({need:.2f} us): the ADC window does not fit inside the ramp."
        )
    if cfg.freq_slope_mhz_us > 100 or cfg.freq_slope_mhz_us < 1:
        problems.append(
            f"freqSlopeConst {cfg.freq_slope_mhz_us} MHz/us is outside a plausible "
            f"range -- check the profileCfg field ORDER (slope is field 8)."
        )
    f_end = cfg.start_freq_ghz + cfg.freq_slope_mhz_us * cfg.ramp_end_time_us / 1000.0
    if f_end > 64.0:
        problems.append(
            f"sweep ends at {f_end:.2f} GHz, above the 64 GHz band edge for xWR6843."
        )
    # Doppler alias check -- the gen-3 defect.
    return problems


# ======================================================================
# PART A -- codebook sizing (NO HARDWARE NEEDED)
# ======================================================================

def size_codebook(cfg: RadarCfg,
                  slope_min: float = 40.0,
                  slope_max: float = 70.0,
                  df_span_khz: float = 2000.0) -> dict:
    """
    How many DISTINGUISHABLE states does each challenge component provide?

    The binding test asks whether a return could have been produced by the
    challenge actually transmitted. A component is only useful if a wrong
    response is *observably* wrong. The three components differ sharply:

      slope  : a response built with slope s' dechirps against s as a
               residual LFM of bandwidth |s-s'| * T_adc. Once that exceeds
               one range bin the energy SPREADS -> strong decoherence.
      df     : a start-frequency offset produces a constant beat offset,
               which SHIFTS the target rather than spreading it. Weaker:
               an attacker that guesses wrong still yields a clean peak,
               just at the wrong range. Useful mainly in combination.
      perm   : a wrong chirp order scrambles the phase progression across
               the frame -> energy spreads in DOPPLER. Strong, and cheap.
    """
    T = cfg.adc_window_us * 1e-6
    bin_hz = cfg.bin_hz

    # --- slope: minimum step that spreads energy by >= 1 range bin --------
    d_slope_hz_per_s = bin_hz / T                 # Hz/s
    d_slope_mhz_us = d_slope_hz_per_s / 1e12
    n_slope = max(1, int((slope_max - slope_min) / d_slope_mhz_us))

    # --- start frequency: step that shifts by >= 1 range bin -------------
    # constant beat offset of bin_hz corresponds to df = bin_hz
    d_df_khz = bin_hz / 1e3
    n_df = max(1, int(df_span_khz / d_df_khz))

    # --- permutation: distinct orderings of the chirps in a frame ---------
    n_chirps = cfg.chirps_per_frame
    # log2 of n! without overflow
    log2_perm = float(np.sum(np.log2(np.arange(1, n_chirps + 1)))) if n_chirps > 1 else 0.0

    total_log2 = np.log2(n_slope) + np.log2(n_df) + log2_perm
    beta_floor = 2.0 ** (-total_log2)

    return dict(
        slope_step_mhz_us=d_slope_mhz_us,
        n_slope=n_slope,
        df_step_khz=d_df_khz,
        n_df=n_df,
        n_chirps=n_chirps,
        log2_perm=log2_perm,
        total_log2=total_log2,
        beta_floor=beta_floor,
    )


def bound_table(beta: float, alpha_f: float = 1e-2,
                K_list=(3, 4, 5), L_list=(2, 3, 4)) -> list[dict]:
    """
    Theorem 6.7 in the homogeneous case, INCLUDING the quorum multiplicity
    N_L(K) that the union bound requires:

        Pr[forge] <= N_L(K) * alpha_F * beta^(L - min(L, q_act))

    Reported for the strongest interesting case q_act = 0 (attacker covers
    no anchor causally) so the challenge term is fully exercised.
    """
    from math import comb
    rows = []
    for K in K_list:
        for L in L_list:
            if L > K:
                continue
            N = sum(comb(K, m) for m in range(L, K + 1))
            rows.append(dict(K=K, L=L, N=N,
                             bound=N * alpha_f * (beta ** L)))
    return rows


def cmd_design(args) -> None:
    cfg = parse_cfg(args.cfg) if args.cfg else RadarCfg(
        start_freq_ghz=60.0, idle_time_us=200.0, adc_start_time_us=7.0,
        ramp_end_time_us=57.14, freq_slope_mhz_us=57.14,
        num_adc_samples=256, sample_rate_ksps=5209.0,
        chirp_start_idx=0, chirp_end_idx=0, num_loops=16,
        frame_period_ms=33.33)

    print("=" * 70)
    print("PART A -- CHALLENGE CODEBOOK SIZING (no hardware required)")
    print("=" * 70)
    print("\nConfiguration")
    print(cfg.summary())

    probs = sanity_check_cfg(cfg)
    print("\nConfig sanity")
    if probs:
        for p in probs:
            print(f"  [FAIL] {p}")
    else:
        print("  [ok] no structural problems found")

    # Doppler alias warning -- the gen-3 defect, generalised.
    print("\nDoppler observability")
    lam = cfg.wavelength_m
    fp = cfg.frame_period_ms * 1e-3
    print(f"  wavelength {lam*1000:.2f} mm | frame period {fp*1e3:.2f} ms")
    print("  velocities whose inter-frame Doppler phase aliases to ~0"
          " (AVOID as ground truth):")
    for k in range(1, 5):
        v = k * lam / (2.0 * fp)
        print(f"    v = {v:.4f} m/s   ({k} cycle{'s' if k > 1 else ''} per frame)")
    v_max_chirp = lam / (4.0 * cfg.chirp_period_us * 1e-6)
    print(f"  unambiguous velocity from chirp-to-chirp phase: +/-{v_max_chirp:.2f} m/s")

    r = size_codebook(cfg)
    print("\nDistinguishable challenge states")
    print(f"  slope : step {r['slope_step_mhz_us']:.4f} MHz/us for 1-bin spreading"
          f"  -> ~{r['n_slope']} states over 40-70 MHz/us   [STRONG: spreads energy]")
    print(f"  df    : step {r['df_step_khz']:.2f} kHz for a 1-bin shift"
          f"          -> ~{r['n_df']} states over 2 MHz        [WEAK: shifts, not spreads]")
    print(f"  perm  : {r['n_chirps']} chirps/frame"
          f" -> log2({r['n_chirps']}!) = {r['log2_perm']:.1f} bits    [STRONG: spreads in Doppler]")
    print(f"\n  combined entropy  ~{r['total_log2']:.1f} bits")
    print(f"  guessing floor    beta_i >= 2^-{r['total_log2']:.1f} = {r['beta_floor']:.3e}")

    print("\nTheorem 6.7 with this beta (alpha_F = 1e-2, q_act = 0)")
    print(f"  {'K':>3} {'L':>3} {'N_L(K)':>7}   Pr[forge] <=")
    for row in bound_table(min(r['beta_floor'], 0.5)):
        print(f"  {row['K']:>3} {row['L']:>3} {row['N']:>7}   {row['bound']:.3e}")

    print("\nCRITICAL CAVEAT")
    print("  These are INFORMATION-THEORETIC state counts. The number you can")
    print("  actually use is bounded by what the SDK will reprogram between")
    print("  frames. profileCfg holds at most 4 profiles; changing slope or")
    print("  start frequency beyond those 4 generally needs sensorStop/Start,")
    print("  which breaks DCA1000 streaming. The chirp PERMUTATION and the")
    print("  per-chirp TX phase shifter live in the chirp table and are the")
    print("  realistic candidates for per-frame variation via the dynamic")
    print("  chirp API. Measure this first -- it is the gating experiment.")
    print("  If only ~4 profiles are reachable, beta_i >= 0.25 and the")
    print("  challenge term of Theorem 6.7 is nearly worthless: the paper")
    print("  would then have to rest on permutation entropy and geometry.")


# ======================================================================
# PART B -- capture ingestion and metrics
# ======================================================================

def load_capture(path: str, cfg: RadarCfg, layout: str = "dca1000") -> np.ndarray:
    """
    Return a complex cube [frames, chirps, rx, samples].

    layout="dca1000": TI DCA1000 LVDS packing (2 lanes, complex) -- groups of
                      two I samples then two Q samples. This is what
                      readDCA1000.m implements and what real captures use.
    layout="simple" : plain interleaved Q,I -- what the gen-3 emulator writes.
    """
    raw = np.fromfile(path, dtype="<i2")
    ns, nrx = cfg.num_adc_samples, cfg.num_rx
    nch = cfg.chirps_per_frame

    if layout == "simple":
        comp = raw[1::2].astype(np.float64) + 1j * raw[0::2].astype(np.float64)
    elif layout == "dca1000":
        if raw.size % 4:
            raise ValueError("file length is not a multiple of 4 int16 (LVDS group)")
        g = raw.reshape(-1, 4).astype(np.float64)
        i_part = np.stack([g[:, 0], g[:, 1]], axis=1).reshape(-1)
        q_part = np.stack([g[:, 2], g[:, 3]], axis=1).reshape(-1)
        comp = i_part + 1j * q_part
    else:
        raise ValueError(f"unknown layout {layout!r}")

    per_frame = nch * nrx * ns
    nframes = comp.size // per_frame
    if nframes == 0:
        raise ValueError(
            f"file holds {comp.size} complex samples, one frame needs {per_frame}"
        )
    comp = comp[: nframes * per_frame]
    # DCA1000 orders within a chirp as [rx0 samples, rx1 samples, ...]
    return comp.reshape(nframes, nch, nrx, ns)


@dataclass
class CaptureMetrics:
    label: str
    peak_bin: int = 0
    est_range_m: float = 0.0
    range_err_m: float = 0.0
    snr_db: float = 0.0
    noise_floor: float = 0.0
    mainlobe_bins: float = 0.0
    isl_db: float = 0.0
    rx_gain: list = field(default_factory=list)
    rx_phase_deg: list = field(default_factory=list)
    est_bearing_deg: float = 0.0
    est_velocity_ms: float = 0.0
    frames: int = 0
    notes: str = ""


def range_metrics(cube: np.ndarray, cfg: RadarCfg,
                  surveyed_range_m: float, label: str) -> CaptureMetrics:
    win = np.hanning(cfg.num_adc_samples)
    R = np.fft.fft(cube * win, axis=-1)
    half = cfg.num_adc_samples // 2
    prof = np.abs(R).mean(axis=(0, 1, 2))[:half]

    exp_bin = cfg.range_to_bin(surveyed_range_m)
    lo, hi = max(3, int(exp_bin) - 6), min(half, int(exp_bin) + 7)
    pk = lo + int(np.argmax(prof[lo:hi])) if hi > lo else int(np.argmax(prof[3:half])) + 3

    # parabolic interpolation for sub-bin peak
    if 1 <= pk < half - 1:
        y0, y1, y2 = prof[pk - 1], prof[pk], prof[pk + 1]
        denom = (y0 - 2 * y1 + y2)
        delta = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
    else:
        delta = 0.0
    pk_frac = pk + float(np.clip(delta, -0.5, 0.5))

    guard = 8
    mask = np.ones(half, dtype=bool)
    mask[max(0, pk - guard): pk + guard + 1] = False
    mask[:3] = False                      # exclude coupling/DC
    noise = prof[mask].mean()
    snr_db = 20.0 * np.log10(prof[pk] / noise) if noise > 0 else float("nan")

    thr = prof[pk] / np.sqrt(2.0)
    l = pk
    while l > 0 and prof[l] > thr:
        l -= 1
    r = pk
    while r < half - 1 and prof[r] > thr:
        r += 1
    isl = 10.0 * np.log10(prof[mask].sum() / prof[max(0, pk - guard): pk + guard + 1].sum())

    m = CaptureMetrics(label=label)
    m.peak_bin = pk
    m.est_range_m = cfg.bin_to_range(pk_frac)
    m.range_err_m = m.est_range_m - surveyed_range_m
    m.snr_db = snr_db
    m.noise_floor = noise
    m.mainlobe_bins = float(r - l)
    m.isl_db = isl
    m.frames = cube.shape[0]

    g = np.array([np.abs(R[:, :, rx, pk]).mean() for rx in range(cube.shape[2])])
    m.rx_gain = [round(float(v), 4) for v in (g / g[0])]
    ph = np.unwrap([np.angle(R[:, :, rx, pk].mean()) for rx in range(cube.shape[2])])
    ph = ph - ph[0]
    m.rx_phase_deg = [round(float(v), 2) for v in np.degrees(ph)]

    n = np.arange(cube.shape[2])
    slope_rad = float(np.polyfit(n, ph, 1)[0]) if cube.shape[2] > 1 else 0.0
    s = np.clip(slope_rad / np.pi, -1.0, 1.0)
    m.est_bearing_deg = float(np.degrees(np.arcsin(s)))

    if cube.shape[1] > 1:
        sig = R[:, :, :, pk].mean(axis=2)
        d = [np.angle(np.exp(1j * (np.angle(sig[:, c + 1]) - np.angle(sig[:, c]))))
             for c in range(cube.shape[1] - 1)]
        dph = float(np.mean(d))
        Tc = cfg.chirp_period_us * 1e-6
        m.est_velocity_ms = dph * cfg.wavelength_m / (4.0 * np.pi * Tc)
    return m


def cmd_analyse(args) -> None:
    with open(args.manifest) as fh:
        man = json.load(fh)
    base = os.path.dirname(os.path.abspath(args.manifest))
    surveyed = float(man["surveyed_range_m"])
    layout = man.get("layout", "dca1000")

    print("=" * 70)
    print("PART B -- CHALLENGE COST TABLE")
    print("=" * 70)
    print(f"surveyed range {surveyed} m | layout {layout}\n")

    rows, baseline = [], None
    for c in man["captures"]:
        cfgp = os.path.join(base, c["cfg"])
        binp = os.path.join(base, c["bin"])
        cfg = parse_cfg(cfgp)
        for p in sanity_check_cfg(cfg):
            print(f"  [cfg FAIL: {c['label']}] {p}")
        try:
            cube = load_capture(binp, cfg, layout)
        except Exception as exc:                       # noqa: BLE001
            print(f"  [skip {c['label']}] {exc}")
            continue
        m = range_metrics(cube, cfg, surveyed, c["label"])
        m.notes = json.dumps(c.get("challenge", {}), separators=(",", ":"))
        rows.append(m)
        if c["label"] == man.get("baseline_label", "baseline"):
            baseline = m

    if not rows:
        print("no captures analysed")
        return

    hdr = (f"{'label':<14}{'bin':>5}{'range m':>9}{'err cm':>8}"
           f"{'SNR dB':>8}{'lobe':>6}{'ISL dB':>8}{'bearing':>9}{'v m/s':>8}")
    print(hdr)
    print("-" * len(hdr))
    for m in rows:
        print(f"{m.label:<14}{m.peak_bin:>5}{m.est_range_m:>9.3f}"
              f"{100*m.range_err_m:>8.2f}{m.snr_db:>8.2f}{m.mainlobe_bins:>6.1f}"
              f"{m.isl_db:>8.2f}{m.est_bearing_deg:>9.2f}{m.est_velocity_ms:>8.3f}")

    if baseline is not None:
        print(f"\nCost relative to '{baseline.label}':")
        print(f"{'label':<14}{'dSNR dB':>9}{'d lobe':>8}{'d ISL dB':>10}{'d range cm':>12}")
        print("-" * 53)
        for m in rows:
            print(f"{m.label:<14}{m.snr_db-baseline.snr_db:>9.2f}"
                  f"{m.mainlobe_bins-baseline.mainlobe_bins:>8.1f}"
                  f"{m.isl_db-baseline.isl_db:>10.2f}"
                  f"{100*(m.range_err_m-baseline.range_err_m):>12.2f}")

    print("\nRX frontend vector (should be CONSTANT across challenges --")
    print("it is a property of the board, not of the waveform):")
    for m in rows:
        print(f"  {m.label:<14} gain {m.rx_gain}  phase {m.rx_phase_deg}")

    if args.latex:
        with open(args.latex, "w") as fh:
            fh.write("% auto-generated by mosaic_challenge_bench.py\n")
            fh.write("\\begin{table}[t]\n\\centering\\small\n")
            fh.write("\\caption{Measured sensing cost of each challenge component "
                     "on IWR6843ISK + DCA1000.}\n\\label{tab:codebook-cost}\n")
            fh.write("\\begin{tabular}{lrrrr}\n\\toprule\n")
            fh.write("Challenge & SNR (dB) & Main lobe & ISL (dB) & Range err (cm)\\\\\n")
            fh.write("\\midrule\n")
            for m in rows:
                fh.write(f"{m.label} & {m.snr_db:.2f} & {m.mainlobe_bins:.1f} & "
                         f"{m.isl_db:.2f} & {100*m.range_err_m:.2f}\\\\\n")
            fh.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
        print(f"\nLaTeX table written to {args.latex}")


# ======================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("design", help="codebook sizing (no hardware)")
    d.add_argument("--cfg", help="optional TI .cfg to size against")
    d.set_defaults(func=cmd_design)

    a = sub.add_parser("analyse", help="ingest captures, emit cost table")
    a.add_argument("manifest")
    a.add_argument("--latex", help="also write a LaTeX table here")
    a.set_defaults(func=cmd_analyse)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
