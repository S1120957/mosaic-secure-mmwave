from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from mosaic.adapters.base import CapturedFrame, RadarAnchorAdapter
from mosaic.models import Challenge, Observation
from mosaic.signal_processing import estimate_proxy_binding_statistic


class TIRawCaptureConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    adc_samples: int = Field(gt=0)
    chirps_per_frame: int = Field(gt=0)
    rx_channels: int = Field(gt=0)
    adc_bits: int = Field(default=16)
    complex_samples: bool = True
    iq_order: str = "IQ"
    lane_interleave: bool = False
    scale_to_unit: bool = True

    @property
    def complex_values_per_frame(self) -> int:
        return self.adc_samples * self.chirps_per_frame * self.rx_channels

    @property
    def int16_values_per_frame(self) -> int:
        multiplier = 2 if self.complex_samples else 1
        return self.complex_values_per_frame * multiplier

    @property
    def bytes_per_frame(self) -> int:
        return self.int16_values_per_frame * 2


@dataclass(frozen=True)
class TIRawFrame:
    frame_index: int
    samples: np.ndarray


class DCA1000BinaryReader:
    """Offline reader for raw int16 ADC captures exported by DCA1000.

    The parser targets the common complex-IQ capture layout and deliberately
    makes layout assumptions explicit in TIRawCaptureConfig. TI capture options
    must be recorded in the acquisition manifest because LVDS lane and IQ layout
    vary with radar/capture configuration.
    """

    def __init__(self, path: Path, config: TIRawCaptureConfig) -> None:
        self.path = path
        self.config = config
        if not path.exists():
            raise FileNotFoundError(path)
        if config.adc_bits != 16:
            raise NotImplementedError("Phase-C parser currently supports 16-bit ADC only")

    def frame_count(self) -> int:
        size = self.path.stat().st_size
        if size % self.config.bytes_per_frame != 0:
            raise ValueError(
                f"Capture size {size} is not divisible by expected frame size "
                f"{self.config.bytes_per_frame}. Check ADC samples, chirps, RX mask, "
                "IQ order, and LVDS configuration."
            )
        return size // self.config.bytes_per_frame

    def frames(self) -> Iterator[TIRawFrame]:
        raw = np.fromfile(self.path, dtype="<i2")
        per_frame = self.config.int16_values_per_frame
        count = self.frame_count()

        for frame_index in range(count):
            values = raw[frame_index * per_frame : (frame_index + 1) * per_frame]
            samples = self._decode_frame(values)
            yield TIRawFrame(frame_index=frame_index, samples=samples)

    def _decode_frame(self, values: np.ndarray) -> np.ndarray:
        cfg = self.config
        if cfg.lane_interleave:
            raise NotImplementedError(
                "Lane-interleaved DCA1000 decoding must be implemented after the "
                "exact capture mode is confirmed."
            )

        if cfg.complex_samples:
            pairs = values.reshape(-1, 2)
            if cfg.iq_order.upper() == "IQ":
                complex_values = pairs[:, 0].astype(np.float32) + 1j * pairs[:, 1].astype(
                    np.float32
                )
            elif cfg.iq_order.upper() == "QI":
                complex_values = pairs[:, 1].astype(np.float32) + 1j * pairs[:, 0].astype(
                    np.float32
                )
            else:
                raise ValueError("iq_order must be IQ or QI")
        else:
            complex_values = values.astype(np.float32).astype(np.complex64)

        if cfg.scale_to_unit:
            complex_values = complex_values / 32768.0

        # Common logical shape: [chirp/slow-time, ADC/fast-time, RX].
        return complex_values.reshape(
            cfg.chirps_per_frame,
            cfg.adc_samples,
            cfg.rx_channels,
        ).astype(np.complex64)


def estimate_ti_observation(
    samples: np.ndarray,
    *,
    sample_rate_hz: float,
    frequency_slope_hz_per_s: float,
    carrier_frequency_hz: float,
    chirp_period_s: float,
    antenna_spacing_m: float | None = None,
) -> Observation:
    """Basic offline FMCW estimator for capture sanity checking.

    It is intentionally simple and is not the final paper signal-processing
    pipeline. It verifies that the capture has plausible range, Doppler, and
    optional azimuth structure.
    """
    if samples.ndim != 3:
        raise ValueError("Expected samples shaped [chirps, ADC samples, RX]")
    c0 = 299_792_458.0
    chirps, adc_samples, rx = samples.shape

    window_fast = np.hanning(adc_samples)[None, :, None]
    range_fft = np.fft.fft(samples * window_fast, axis=1)
    positive = range_fft[:, : adc_samples // 2, :]
    energy = np.mean(np.abs(positive) ** 2, axis=(0, 2))
    peak_bin = int(np.argmax(energy[1:]) + 1)

    beat_frequency_hz = peak_bin * sample_rate_hz / adc_samples
    range_m = c0 * beat_frequency_hz / (2.0 * frequency_slope_hz_per_s)

    slow_signal = np.mean(positive[:, peak_bin, :], axis=1)
    slow_phase = np.unwrap(np.angle(slow_signal))
    slow_slope = np.polyfit(np.arange(chirps), slow_phase, 1)[0]
    doppler_hz = slow_slope / (2.0 * math.pi * chirp_period_s)
    wavelength_m = c0 / carrier_frequency_hz
    radial_velocity_mps = doppler_hz * wavelength_m / 2.0

    bearing_rad = 0.0
    bearing_std = 0.30
    if rx >= 2 and antenna_spacing_m is not None and antenna_spacing_m > 0:
        antenna_signal = np.mean(positive[:, peak_bin, :], axis=0)
        phase = np.unwrap(np.angle(antenna_signal))
        phase_step = float(np.polyfit(np.arange(rx), phase, 1)[0])
        sin_theta = np.clip(
            phase_step * wavelength_m / (2.0 * math.pi * antenna_spacing_m),
            -1.0,
            1.0,
        )
        bearing_rad = float(math.asin(sin_theta))
        bearing_std = 0.15

    return Observation(
        range_m=max(0.001, float(range_m)),
        radial_velocity_mps=float(radial_velocity_mps),
        bearing_rad=bearing_rad,
        range_std_m=0.20,
        radial_velocity_std_mps=0.20,
        bearing_std_rad=bearing_std,
    )


class OfflineIWR6843Adapter(RadarAnchorAdapter):
    """Adapter that replays a DCA1000 file through the MOSAIC interface."""

    def __init__(
        self,
        *,
        anchor_id: str,
        capture_path: Path,
        raw_config: TIRawCaptureConfig,
        challenge_schedule: dict[int, Challenge],
        sample_rate_hz: float,
        frequency_slope_hz_per_s: float,
        carrier_frequency_hz: float,
        chirp_period_s: float,
        antenna_spacing_m: float | None = None,
    ) -> None:
        self.anchor_id = anchor_id
        self.reader = DCA1000BinaryReader(capture_path, raw_config)
        self._frames = list(self.reader.frames())
        self.challenge_schedule = challenge_schedule
        self.sample_rate_hz = sample_rate_hz
        self.frequency_slope_hz_per_s = frequency_slope_hz_per_s
        self.carrier_frequency_hz = carrier_frequency_hz
        self.chirp_period_s = chirp_period_s
        self.antenna_spacing_m = antenna_spacing_m
        self._configured: Challenge | None = None

    def configure_challenge(self, challenge: Challenge) -> None:
        if challenge.anchor_id != self.anchor_id:
            raise ValueError("Challenge belongs to a different anchor")
        self._configured = challenge

    def capture_frame(self, epoch: int) -> CapturedFrame:
        if epoch >= len(self._frames):
            raise IndexError(epoch)
        expected = self.challenge_schedule[epoch]
        if self._configured != expected:
            raise RuntimeError("Expected challenge was not configured before capture")
        frame = self._frames[epoch]
        return CapturedFrame(
            anchor_id=self.anchor_id,
            epoch=epoch,
            challenge=expected,
            timestamp_ns=epoch,
            sample_buffer=frame.samples.tobytes(order="C"),
        )

    def compute_binding_statistic(self, frame: CapturedFrame) -> float:
        samples = np.frombuffer(frame.sample_buffer, dtype=np.complex64).reshape(
            self._frames[frame.epoch].samples.shape
        )
        # Software plumbing proxy only. Replace with challenge-specific TI
        # dechirp/coherence implementation once live configuration is verified.
        return estimate_proxy_binding_statistic(
            np.real(samples).astype(np.float32),
            challenge=frame.challenge,
        )

    def estimate_observation(self, frame: CapturedFrame) -> Observation:
        shape = self._frames[frame.epoch].samples.shape
        samples = np.frombuffer(frame.sample_buffer, dtype=np.complex64).reshape(shape)
        return estimate_ti_observation(
            samples,
            sample_rate_hz=self.sample_rate_hz,
            frequency_slope_hz_per_s=self.frequency_slope_hz_per_s,
            carrier_frequency_hz=self.carrier_frequency_hz,
            chirp_period_s=self.chirp_period_s,
            antenna_spacing_m=self.antenna_spacing_m,
        )
