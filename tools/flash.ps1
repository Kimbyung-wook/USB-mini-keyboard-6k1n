<#
.SYNOPSIS
  Waits for the CH552 ROM bootloader (4348:55E0) and flashes a .hex the moment it appears.

.DESCRIPTION
  The bootloader leaves after about 5 seconds without traffic, so the uploader
  (CH55xduino's vnproch55x) is started first and keeps retrying (-r) until the
  device shows up and its WCH driver is ready. Polling Windows for the device first
  is not enough: it can be listed before the driver opens, and the upload then fails
  with "CH375GetUsbID 0 / No CH55x USB Found".
  The bootloader entry pin is written together with the firmware:
    P15 (default) = hold key D (P1.5) while plugging in
    P36           = D+ pull-up (1.5-2 kOhm between chip pin 12 and pin 16)

.EXAMPLE
  .\tools\flash.ps1 -Hex firmware\test_pinmap\build\CH55xDuino.mcs51.ch552\test_pinmap.ino.hex
#>
param(
    [Parameter(Mandatory = $true)][string]$Hex,
    [ValidateSet('P15', 'P36')][string]$BootPin = 'P15',
    [ValidateRange(1, 255)][int]$TimeoutSec = 60
)

$ErrorActionPreference = 'Stop'

$hexPath = (Resolve-Path $Hex).Path

# Use the newest installed MCS51Tools
$toolsRoot = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\CH55xDuino\tools\MCS51Tools'
$toolDir = Get-ChildItem $toolsRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $toolDir) { throw "CH55xDuino MCS51Tools not found under $toolsRoot" }
$exe = Join-Path $toolDir.FullName 'win\vnproch55x.exe'

# vnproch55x config byte: 1 = P1.5 pull-down, 3 = P3.6 (D+) pull-up
$bootCfg = if ($BootPin -eq 'P15') { 1 } else { 3 }

Write-Host "hex      : $hexPath"
Write-Host "uploader : $exe"
Write-Host "boot pin : $BootPin (config $bootCfg)"
Write-Host ""
if ($BootPin -eq 'P15') {
    Write-Host "Plug the keyboard in while holding key D (P1.5)..."
} else {
    Write-Host "Plug the keyboard in with the D+ pull-up connected..."
}

Write-Host "(waiting up to $TimeoutSec s, started $(Get-Date -Format HH:mm:ss))"

# vnproch55x retries every ~0.1 s for -r seconds, then flashes as soon as it opens the device
& $exe -r $TimeoutSec -t CH552 -c $bootCfg $hexPath
$code = $LASTEXITCODE
Write-Host "vnproch55x exit code: $code"
exit $code
