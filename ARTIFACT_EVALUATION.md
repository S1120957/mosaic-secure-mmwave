# Reviewer artifact: physical single-anchor capture

Run the complete Python verification:

```powershell
python -m pip install -e ".[dev]"
pytest
python scripts\verify_real_data.py
```

Run the independent C++ validator:

```powershell
cmake -S cpp -B build\cpp
cmake --build build\cpp --config Release
.\build\cpp\Release\validate_real_data.exe `
  data\real-data\iwr6843-dca1000-session01\adc_data.bin `
  data\real-data\iwr6843-dca1000-session01\adc_data_bg.bin
```

Expected results:

- target and background hashes match `SHA256SUMS`;
- each file contains 10 complete frames;
- each decoded frame has shape `[16, 256, 4]`;
- strongest target-minus-background range peak is bin 46;
- bin 13 is recovered for the secondary target;
- the overall verification result is `true`.

See `docs/REAL_DATA_REPRODUCIBILITY.md` for scope and limitations.
