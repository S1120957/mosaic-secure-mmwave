param([Parameter(Mandatory=$true)][ValidateSet("session02","session03")][string]$Session)
$Repo = "C:\Users\tariq\Downloads\MobiCom\github\mosaic-secure-mmwave"
$SessionDir = Join-Path $Repo "data\measured\challenge-feasibility\$Session"
Write-Host "Capture session directory: $SessionDir"
Write-Host "Use profile_P0_P1_advframe.cfg for both target and background captures."
Write-Host "Required output size per binary: 131072000 bytes"
Write-Host "Required subframes: 2000 (1000 P0 / 1000 P1)"
Write-Host "After copying outputs, run:"
Write-Host "python scripts\validate_repeat_session.py `"$SessionDir`""
