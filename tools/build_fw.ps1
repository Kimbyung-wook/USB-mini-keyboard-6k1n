<#
.SYNOPSIS
  Builds the macro_keyboard firmware with the build date written into it.

.DESCRIPTION
  Runs the arduino-cli bundled with Arduino IDE 2 (or the one on PATH) with
  the board options from firmware\macro_keyboard\README.md, and passes the
  current time as -DFW_BUILD_YEAR=... flags so HELLO (and the GUI) report it.
  The version itself is FW_MAJOR/FW_MINOR/FW_PATCH in src\config.h.

  A build from the Arduino IDE works too, but has no build date (the GUI
  shows "날짜 없음").

  -Board picks the board file (firmware\macro_keyboard\src\boards\<board>.h,
  docs\BOARD_INFO.md); gui\boards.py uses the same board names.

  Result: firmware\macro_keyboard\build\macro_keyboard.ino.hex, ready for
  tools\flash.ps1, and a copy named macro_keyboard-<BOARD>.hex, the file the
  GUI's firmware update window offers first for that board.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\build_fw.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\build_fw.ps1 -Board mk6k1n
#>
param(
    [ValidateSet('mk6k1n')]
    [string]$Board = 'mk6k1n'
)

# Board options of each board file
$fqbns = @{
    mk6k1n = 'CH55xDuino:mcs51:ch552:usb_settings=user266,bootloader_pin=p15'
}
$Fqbn = $fqbns[$Board]
$boardName = $Board.ToUpper()

$ErrorActionPreference = 'Stop'

$root = Split-Path $PSScriptRoot -Parent
$sketch = Join-Path $root 'firmware\macro_keyboard'
$outDir = Join-Path $sketch 'build'

$cli = Join-Path $env:LOCALAPPDATA 'Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'
if (-not (Test-Path $cli)) {
    $onPath = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if (-not $onPath) { throw "arduino-cli not found (install Arduino IDE 2 or put arduino-cli on PATH)" }
    $cli = $onPath.Source
}

# Plain numbers without leading zeros (08 would be an invalid octal literal in C)
$now = Get-Date
$flags = "-DFW_BUILD_YEAR=$($now.Year) -DFW_BUILD_MONTH=$($now.Month) -DFW_BUILD_DAY=$($now.Day)" +
         " -DFW_BUILD_HOUR=$($now.Hour) -DFW_BUILD_MINUTE=$($now.Minute) -DBOARD_$boardName"

# build.extra_flags is taken by the board menu (USB settings), so use the
# compiler hooks that CH55xDuino leaves empty
& $cli compile --fqbn $Fqbn --build-property "compiler.c.extra_flags=$flags" `
    --build-property "compiler.cpp.extra_flags=$flags" --output-dir $outDir $sketch
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed (exit code $LASTEXITCODE)"
    exit $LASTEXITCODE
}
$boardHex = Join-Path $outDir "macro_keyboard-$boardName.hex"
Copy-Item (Join-Path $outDir 'macro_keyboard.ino.hex') $boardHex -Force
Write-Host ""
Write-Host "Built $boardName with build date $($now.ToString('yyyy-MM-dd HH:mm')) -> $boardHex"
