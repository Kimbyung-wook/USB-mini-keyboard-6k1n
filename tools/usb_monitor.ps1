<#
.SYNOPSIS
  Logs USB/HID devices that appear or disappear, or shows when the keyboard was last seen.

.DESCRIPTION
  Default mode: records every USB/HID device that was not present at start,
  for -Seconds seconds. Use it while plugging the keyboard in to see whether
  Windows detects anything at all (even an "unknown device").

  -History: prints the last arrival/removal time of the devices this project
  uses, which also catches devices that were present only for a moment
  (the bootloader stays about 5 seconds).
    4348:55E0  CH552 ROM bootloader
    1209:C55D  test / project firmware

.EXAMPLE
  .\tools\usb_monitor.ps1 -Seconds 180
  .\tools\usb_monitor.ps1 -History
#>
param(
    [int]$Seconds = 180,
    [switch]$History
)

if ($History) {
    Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_4348&PID_55E0|VID_1209&PID_C55D' } | ForEach-Object {
        $arrive = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_LastArrivalDate' -ErrorAction SilentlyContinue).Data
        $remove = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_LastRemovalDate' -ErrorAction SilentlyContinue).Data
        $service = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Service' -ErrorAction SilentlyContinue).Data
        "{0} | {1} | {2} | driver={3} | arrive={4} | remove={5}" -f $_.InstanceId, $_.FriendlyName, $_.Status, $service, $arrive, $remove
    }
    exit 0
}

$isUsbOrHid = { $_.InstanceId -like 'USB\*' -or $_.InstanceId -like 'HID\*' }

$baseline = @{}
Get-PnpDevice -PresentOnly | Where-Object $isUsbOrHid | ForEach-Object { $baseline[$_.InstanceId] = 1 }

Write-Host "Monitoring for $Seconds s from $(Get-Date -Format HH:mm:ss). Plug/unplug the keyboard now."
$seen = @{}
$end = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $end) {
    $present = @{}
    foreach ($d in (Get-PnpDevice -PresentOnly | Where-Object $isUsbOrHid)) {
        $present[$d.InstanceId] = 1
        if (-not $baseline.ContainsKey($d.InstanceId) -and -not $seen.ContainsKey($d.InstanceId)) {
            $seen[$d.InstanceId] = 1
            "{0:HH:mm:ss.f} + {1} | {2} | {3}" -f (Get-Date), $d.InstanceId, $d.FriendlyName, $d.Status
        }
    }
    foreach ($id in @($seen.Keys)) {
        if (-not $present.ContainsKey($id)) {
            "{0:HH:mm:ss.f} - {1}" -f (Get-Date), $id
            $seen.Remove($id)
        }
    }
    Start-Sleep -Milliseconds 300
}
Write-Host "Done."
