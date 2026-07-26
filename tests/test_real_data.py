from pathlib import Path

import numpy as np
import yaml

from mosaic.adapters.ti_iwr6843 import DCA1000BinaryReader, TIRawCaptureConfig
from mosaic.real_data import verify_real_capture_pair


ROOT = Path(__file__).parents[1]


def test_qi_chirp_rx_sample_layout_matches_exported_values():
    cfg = TIRawCaptureConfig(
        adc_samples=256,
        chirps_per_frame=16,
        rx_channels=4,
        adc_bits=16,
        complex_samples=True,
        iq_order="QI",
        sample_order="chirp_rx_sample",
        lane_interleave=False,
        scale_to_unit=False,
    )
    path = ROOT / "data/real-data/iwr6843-dca1000-session01/adc_data.bin"
    frame = next(DCA1000BinaryReader(path, cfg).frames()).samples
    assert frame.shape == (16, 256, 4)
    assert frame.dtype == np.complex64
    assert frame[0, 0, 0] == np.complex64(1839 + 101j)
    assert frame[0, 1, 0] == np.complex64(1070 + 1214j)
    assert frame[0, 0, 1] == np.complex64(405 + 1574j)


def test_real_capture_pair_reproduces_ground_truth_bins(tmp_path):
    report = verify_real_capture_pair(
        profile_path=ROOT / "configs/ti_iwr6843isk_ods_real_capture.yaml",
        output_report=tmp_path / "report.json",
        output_spectrum_csv=tmp_path / "spectrum.csv",
    )
    assert report["overall_pass"]
    checks = {item["target_id"]: item for item in report["target_checks"]}
    assert checks["Target_1"]["observed_local_peak_bin"] == 46
    assert checks["Target_2"]["observed_local_peak_bin"] == 13
    assert report["challenge_profile_identity"]["verified_for_this_capture"] is False
