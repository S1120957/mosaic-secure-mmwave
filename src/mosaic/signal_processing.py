from __future__ import annotations

import math
import numpy as np

from mosaic.models import Observation


def synthetic_fmcw_buffer(
    *,
    range_m: float,
    radial_velocity_mps: float,
    bearing_rad: float,
    frames: int = 16,
    fast_time_samples: int = 128,
    antennas: int = 4,
    noise_std: float = 0.05,
    rng: np.random.Generator,
) -> np.ndarray:
    """Create a deterministic research-only proxy buffer.

    This is not a calibrated radar simulator. It provides a stable recorded-data
    format and a non-trivial replay path before physical hardware is connected.
    """
    n = np.arange(fast_time_samples, dtype=np.float32)
    k = np.arange(frames, dtype=np.float32)
    m = np.arange(antennas, dtype=np.float32)

    range_bin = np.clip(range_m * 6.0, 1.0, fast_time_samples / 2 - 2)
    doppler_cycles = np.clip(radial_velocity_mps * 0.08, -0.35, 0.35)
    spatial_cycles = 0.25 * math.sin(bearing_rad)

    phase = (
        2 * np.pi * range_bin * n[None, :, None] / fast_time_samples
        + 2 * np.pi * doppler_cycles * k[:, None, None]
        + 2 * np.pi * spatial_cycles * m[None, None, :]
    )
    signal = np.cos(phase) + 0.2 * np.cos(2 * phase + 0.3)
    noise = rng.normal(0.0, noise_std, size=signal.shape)
    return (signal + noise).astype(np.float32)


def estimate_proxy_observation(
    samples: np.ndarray,
    *,
    range_scale_m_per_bin: float = 1.0 / 6.0,
) -> Observation:
    """Estimate proxy range, velocity, and bearing from a recorded buffer.

    Used only to test the end-to-end recording/replay interface. Replace this
    function with the selected radar SDK's calibrated processing pipeline.
    """
    if samples.ndim != 3:
        raise ValueError("Expected [slow_time, fast_time, antennas] samples")

    slow, fast, antennas = samples.shape
    range_fft = np.fft.rfft(samples, axis=1)
    energy_by_bin = np.mean(np.abs(range_fft) ** 2, axis=(0, 2))
    peak_bin = int(np.argmax(energy_by_bin[1:]) + 1)
    range_m = peak_bin * range_scale_m_per_bin

    complex_slow = range_fft[:, peak_bin, :].mean(axis=1)
    slow_phase = np.unwrap(np.angle(complex_slow))
    slope = np.polyfit(np.arange(slow), slow_phase, 1)[0]
    radial_velocity_mps = float(slope / (2 * np.pi * 0.08))

    complex_ant = range_fft[:, peak_bin, :].mean(axis=0)
    ant_phase = np.unwrap(np.angle(complex_ant))
    spatial_slope = np.polyfit(np.arange(antennas), ant_phase, 1)[0]
    sin_theta = float(np.clip(spatial_slope / (2 * np.pi * 0.25), -1.0, 1.0))
    bearing_rad = float(math.asin(sin_theta))

    return Observation(
        range_m=max(0.001, float(range_m)),
        radial_velocity_mps=radial_velocity_mps,
        bearing_rad=bearing_rad,
        range_std_m=0.15,
        radial_velocity_std_mps=0.20,
        bearing_std_rad=0.08,
    )
