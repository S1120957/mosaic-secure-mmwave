from pathlib import Path

import numpy as np

from mosaic.adapters.ti_iwr6843 import (
    DCA1000BinaryReader,
    TIRawCaptureConfig,
    estimate_ti_observation,
)


def test_dca1000_reader_decodes_complex_iq(tmp_path):
    cfg = TIRawCaptureConfig(
        adc_samples=8,
        chirps_per_frame=4,
        rx_channels=2,
        complex_samples=True,
        iq_order="IQ",
    )
    complex_values = (
        np.arange(cfg.complex_values_per_frame, dtype=np.float32)
        + 1j * np.arange(cfg.complex_values_per_frame, dtype=np.float32)[::-1]
    )
    pairs = np.column_stack(
        [
            complex_values.real.astype("<i2"),
            complex_values.imag.astype("<i2"),
        ]
    ).reshape(-1)
    path = tmp_path / "adc.bin"
    pairs.tofile(path)

    reader = DCA1000BinaryReader(path, cfg)
    frames = list(reader.frames())
    assert reader.frame_count() == 1
    assert frames[0].samples.shape == (4, 8, 2)
    assert np.iscomplexobj(frames[0].samples)


def test_dca1000_rejects_incompatible_file_size(tmp_path):
    cfg = TIRawCaptureConfig(
        adc_samples=8,
        chirps_per_frame=4,
        rx_channels=2,
    )
    path = tmp_path / "bad.bin"
    np.arange(11, dtype="<i2").tofile(path)
    reader = DCA1000BinaryReader(path, cfg)
    try:
        reader.frame_count()
        assert False, "Expected frame-size validation error"
    except ValueError:
        pass


def test_ti_estimator_returns_plausible_observation():
    chirps, adc, rx = 32, 128, 4
    n = np.arange(adc)
    tone_bin = 12
    base = np.exp(1j * 2 * np.pi * tone_bin * n / adc)
    samples = np.tile(base[None, :, None], (chirps, 1, rx)).astype(np.complex64)
    obs = estimate_ti_observation(
        samples,
        sample_rate_hz=5e6,
        frequency_slope_hz_per_s=60e12,
        carrier_frequency_hz=60.25e9,
        chirp_period_s=160e-6,
    )
    assert 0.1 < obs.range_m < 10.0
