from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


# Generation 4 dual-profile FMCW radar emulator.
#
# This script produces synthetic regression fixtures only.
# The generated files are not physical measurements and are not paper-eligible.

SEED = 2026

NUM_SUBFRAMES = 2000
NUM_CHIRPS = 16
NUM_RX = 4
NUM_SAMPLES = 256

SAMPLE_RATE_HZ = 5_209_000.0
SLOPE_HZ_PER_S = 57.14e12
SPEED_OF_LIGHT_MPS = 299_792_458.0

START_FREQ_P0_HZ = 60.000e9
START_FREQ_P1_HZ = 60.100e9

CLUTTER_RANGE_M = 0.694
CLUTTER_BEARING_DEG = 30.0

TARGET_RANGE_M = 2.457
TARGET_VELOCITY_MPS = 0.11
TARGET_BEARING_DEG = 15.0

CHIRP_PERIOD_S = 257.14e-6
SUBFRAME_PERIOD_S = 16.666e-3

DIRECT_COUPLING_AMPLITUDE = 9000.0
DIRECT_COUPLING_NORMALIZED_FREQUENCY = 0.0039

CLUTTER_AMPLITUDE = 3200.0
TARGET_AMPLITUDE = 5000.0
NOISE_STD = 150.0

OUTPUT_DIR = Path("data") / "emulated"
BACKGROUND_PATH = OUTPUT_DIR / "gen4_bg.bin"
TARGET_PATH = OUTPUT_DIR / "gen4_target.bin"


def normalized_beat_frequency(range_m: float) -> float:
    """Return beat frequency normalized by the ADC sampling frequency."""
    beat_frequency_hz = (
        2.0
        * SLOPE_HZ_PER_S
        * range_m
        / SPEED_OF_LIGHT_MPS
    )
    return beat_frequency_hz / SAMPLE_RATE_HZ


def fractional_range_bin(range_m: float) -> float:
    """Return the physical range's fractional FFT-bin location."""
    return normalized_beat_frequency(range_m) * NUM_SAMPLES


def export_bin(
    complex_data: np.ndarray,
    output_path: Path,
) -> tuple[int, str]:
    """Export complex samples in the established emulator Q-then-I layout."""
    if complex_data.shape != (
        NUM_SUBFRAMES,
        NUM_CHIRPS,
        NUM_RX,
        NUM_SAMPLES,
    ):
        raise ValueError(
            "Unexpected complex-data shape: "
            f"{complex_data.shape}"
        )

    # Clip floating-point values before conversion to prevent int16 wrapping.
    q_values = np.clip(
        np.imag(complex_data),
        -32768,
        32767,
    ).astype("<i2")

    i_values = np.clip(
        np.real(complex_data),
        -32768,
        32767,
    ).astype("<i2")

    raw = np.empty(
        complex_data.shape + (2,),
        dtype="<i2",
    )

    raw[..., 0] = q_values
    raw[..., 1] = i_values

    binary = raw.tobytes(order="C")
    output_path.write_bytes(binary)

    return (
        len(binary),
        hashlib.sha256(binary).hexdigest(),
    )


def generate_gen4_dataset() -> None:
    rng = np.random.default_rng(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sample_index = np.arange(
        NUM_SAMPLES,
        dtype=np.float64,
    )

    rx_index = np.arange(
        NUM_RX,
        dtype=np.float64,
    )

    clutter_frequency = normalized_beat_frequency(
        CLUTTER_RANGE_M
    )

    target_frequency = normalized_beat_frequency(
        TARGET_RANGE_M
    )

    # Gen-3 receiver gain and phase imbalance model.
    rx_gain = np.array(
        [1.00, 0.86, 1.14, 0.93],
        dtype=np.float64,
    )

    rx_phase_error_deg = np.array(
        [0.0, 10.3, -6.8, 12.6],
        dtype=np.float64,
    )

    rx_transfer = rx_gain * np.exp(
        1j * np.radians(rx_phase_error_deg)
    )

    # Oscillator random-walk phase drift across subframes.
    phase_drift = np.cumsum(
        rng.normal(
            loc=0.0,
            scale=0.08,
            size=NUM_SUBFRAMES,
        )
    )

    direct_signal = (
        DIRECT_COUPLING_AMPLITUDE
        * np.exp(
            1j
            * 2.0
            * np.pi
            * DIRECT_COUPLING_NORMALIZED_FREQUENCY
            * sample_index
        )
    )

    clutter_spatial = np.exp(
        1j
        * np.pi
        * np.sin(
            np.radians(CLUTTER_BEARING_DEG)
        )
        * rx_index
    )

    target_spatial = np.exp(
        1j
        * np.pi
        * np.sin(
            np.radians(TARGET_BEARING_DEG)
        )
        * rx_index
    )

    clutter_wave = (
        CLUTTER_AMPLITUDE
        * np.exp(
            1j
            * 2.0
            * np.pi
            * clutter_frequency
            * sample_index
        )
    )

    clutter_field = np.outer(
        clutter_spatial,
        clutter_wave,
    )

    adc_background = np.empty(
        (
            NUM_SUBFRAMES,
            NUM_CHIRPS,
            NUM_RX,
            NUM_SAMPLES,
        ),
        dtype=np.complex128,
    )

    adc_target = np.empty_like(adc_background)

    for subframe_index in range(NUM_SUBFRAMES):
        # Deterministic P0/P1 switching is retained only for regression testing.
        # It is not an unpredictable security challenge.
        is_p1 = subframe_index % 2 != 0
        active_start_frequency_hz = (
            START_FREQ_P1_HZ
            if is_p1
            else START_FREQ_P0_HZ
        )

        frequency_offset_hz = (
            active_start_frequency_hz
            - START_FREQ_P0_HZ
        )

        target_frequency_offset_phase = (
            4.0
            * np.pi
            * frequency_offset_hz
            * TARGET_RANGE_M
            / SPEED_OF_LIGHT_MPS
        )

        subframe_time_s = (
            subframe_index
            * SUBFRAME_PERIOD_S
        )

        oscillator_phase = (
            phase_drift[subframe_index]
            + rng.normal(
                loc=0.0,
                scale=0.01,
            )
        )

        wavelength_m = (
            SPEED_OF_LIGHT_MPS
            / active_start_frequency_hz
        )

        target_doppler_hz = (
            2.0
            * TARGET_VELOCITY_MPS
            / wavelength_m
        )

        for chirp_index in range(NUM_CHIRPS):
            chirp_time_s = (
                subframe_time_s
                + chirp_index
                * CHIRP_PERIOD_S
            )

            target_doppler_phase = (
                2.0
                * np.pi
                * target_doppler_hz
                * chirp_time_s
            )

            target_total_phase = (
                target_doppler_phase
                + target_frequency_offset_phase
            )

            target_wave = (
                TARGET_AMPLITUDE
                * np.exp(
                    1j
                    * (
                        2.0
                        * np.pi
                        * target_frequency
                        * sample_index
                        + target_total_phase
                    )
                )
            )

            target_field = np.outer(
                target_spatial,
                target_wave,
            )

            for rx_index_int in range(NUM_RX):
                background_noise = (
                    rng.normal(
                        loc=0.0,
                        scale=NOISE_STD,
                        size=NUM_SAMPLES,
                    )
                    + 1j
                    * rng.normal(
                        loc=0.0,
                        scale=NOISE_STD,
                        size=NUM_SAMPLES,
                    )
                )

                target_noise = (
                    rng.normal(
                        loc=0.0,
                        scale=NOISE_STD,
                        size=NUM_SAMPLES,
                    )
                    + 1j
                    * rng.normal(
                        loc=0.0,
                        scale=NOISE_STD,
                        size=NUM_SAMPLES,
                    )
                )

                background_rf_field = (
                    direct_signal
                    + clutter_field[rx_index_int]
                )

                target_rf_field = (
                    background_rf_field
                    + target_field[rx_index_int]
                )

                frontend_response = (
                    rx_transfer[rx_index_int]
                    * np.exp(
                        1j * oscillator_phase
                    )
                )

                adc_background[
                    subframe_index,
                    chirp_index,
                    rx_index_int,
                    :,
                ] = (
                    background_rf_field
                    * frontend_response
                    + background_noise
                )

                adc_target[
                    subframe_index,
                    chirp_index,
                    rx_index_int,
                    :,
                ] = (
                    target_rf_field
                    * frontend_response
                    + target_noise
                )

    background_bytes, background_hash = export_bin(
        adc_background,
        BACKGROUND_PATH,
    )

    target_bytes, target_hash = export_bin(
        adc_target,
        TARGET_PATH,
    )

    expected_bytes = (
        NUM_SUBFRAMES
        * NUM_CHIRPS
        * NUM_RX
        * NUM_SAMPLES
        * 2
        * np.dtype("<i2").itemsize
    )

    if background_bytes != expected_bytes:
        raise RuntimeError(
            "Unexpected background size: "
            f"{background_bytes:,}; "
            f"expected {expected_bytes:,}"
        )

    if target_bytes != expected_bytes:
        raise RuntimeError(
            "Unexpected target size: "
            f"{target_bytes:,}; "
            f"expected {expected_bytes:,}"
        )

    if background_hash == target_hash:
        raise RuntimeError(
            "Background and target hashes are identical."
        )

    print("=== GEN-4 EMULATED DATASET COMPLETE ===")
    print(
        "Classification: synthetic/emulated regression fixture; "
        "not physical measurement"
    )
    print(
        f"Clutter fractional bin: "
        f"{fractional_range_bin(CLUTTER_RANGE_M):.6f}"
    )
    print(
        f"Target fractional bin:  "
        f"{fractional_range_bin(TARGET_RANGE_M):.6f}"
    )
    print(
        f"Background: {BACKGROUND_PATH} "
        f"({background_bytes:,} bytes)"
    )
    print(f"SHA-256: {background_hash}")
    print(
        f"Target:     {TARGET_PATH} "
        f"({target_bytes:,} bytes)"
    )
    print(f"SHA-256: {target_hash}")


if __name__ == "__main__":
    generate_gen4_dataset()