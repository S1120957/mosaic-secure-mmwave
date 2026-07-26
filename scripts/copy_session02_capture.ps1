param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("target","background")]
    [string]$Mode,

    [string]$Repo = "C:\Users\tariq\Downloads\MobiCom\github\mosaic-secure-mmwave",

    [string]$CapturedBin,

    [string]$RuntimeLog,

    [string]$TimestampJson
)

$ErrorActionPreference = "Stop"

$SessionDir = Join-Path $Repo "data\measured\challenge-feasibility\session02"
$Config = Join-Path $Repo "configs\challenge\profile_P0_P1_advframe.cfg"

if (-not (Test-Path $Config)) {
    throw "Missing radar configuration: $Config"
}

if (-not (Test-Path $SessionDir)) {
    New-Item -ItemType Directory -Force -Path $SessionDir | Out-Null
}

Write-Host ""
Write-Host "SESSION 02 PHYSICAL CAPTURE"
Write-Host "Mode: $Mode"
Write-Host "Radar config: $Config"
Write-Host "Expected: 2000 subframes, alternating P0/P1"
Write-Host "Expected binary size: 131072000 bytes"
Write-Host ""

if ([string]::IsNullOrWhiteSpace($CapturedBin)) {
    Write-Host "No captured binary path supplied."
    Write-Host "Perform the DCA1000 capture now, then rerun this script with:"
    Write-Host "  -CapturedBin <path-to-new-adc-bin>"
    Write-Host "  -RuntimeLog <path-to-runtime-log>"
    Write-Host "  -TimestampJson <path-to-2000-record-json>"
    exit 2
}

foreach ($Path in @($CapturedBin, $RuntimeLog, $TimestampJson)) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path $Path)) {
        throw "Missing physical capture output: $Path"
    }
}

$DestBin = if ($Mode -eq "target") {
    Join-Path $SessionDir "profile_switch_target_full.bin"
} else {
    Join-Path $SessionDir "profile_switch_bg_full.bin"
}

$Size = (Get-Item $CapturedBin).Length
if ($Size -ne 131072000) {
    throw "Captured binary size is $Size bytes; expected 131072000."
}

Copy-Item $CapturedBin $DestBin -Force
Copy-Item $RuntimeLog (Join-Path $SessionDir "runtime_control_capture.log") -Force
Copy-Item $TimestampJson (Join-Path $SessionDir "per_subframe_timestamps.json") -Force

Write-Host "Copied measured $Mode capture to:"
Write-Host "  $DestBin"
Write-Host ""
Write-Host "After both target and background captures exist, run:"
Write-Host "python scripts\validate_repeat_session.py `"$SessionDir`""
