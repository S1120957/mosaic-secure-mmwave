# TI capture command sequence

The exact mmWave Studio GUI/CLI commands depend on installed TI versions and
board revision. Preserve the generated radar configuration file and DCA1000
logs for every capture.

After TI tools produce `adc_data.bin`, import it with:

```powershell
python scripts\import_ti_dca1000.py `
  --profile configs\ti_iwr6843isk_ods_single_anchor.yaml `
  --source-bin data\raw\ti-a1-benign\adc_data.bin `
  --output data\recorded\ti-a1-benign `
  --anchor-key-hex $env:MOSAIC_A1_KEY_HEX
```

Validate:

```powershell
mosaic validate-recording data\recorded\ti-a1-benign
```

The environment variable should contain 64 hexadecimal characters:

```powershell
$env:MOSAIC_A1_KEY_HEX = python -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit the key or raw recordings.

## Software-only parser test

Create a mock binary with the declared TI layout:

```powershell
python scripts\create_mock_dca1000_capture.py `
  --profile configs\ti_iwr6843isk_ods_single_anchor.yaml `
  --output data\raw\mock-ti\adc_data.bin `
  --frames 12
```

Then import it. The resulting recording remains synthetic and is not paper
evidence.
