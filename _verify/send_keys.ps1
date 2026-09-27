# Temporary Task 4 verification harness. Will be deleted after use.
# Sends REAL keystrokes (keybd_event) at fixed offsets from program start.
param(
    [Parameter(Mandatory = $true)][string]$Mode,      # multikey | heldenter
    [Parameter(Mandatory = $true)][string]$LogFile,
    [Parameter(Mandatory = $true)][int]$AutostartMs,
    [Parameter(Mandatory = $true)][string]$Tag
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Kb {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    public static void Down(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void Up(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
}
'@

$python = "python"
$log = Join-Path $PWD $LogFile
if (Test-Path $log) { Remove-Item -Force $log }

$env:DSH_ENTER_TEST_AUTOSTART_MS = "$AutostartMs"
$script:py = Start-Process $python -ArgumentList 'main.py' -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError (Join-Path $PWD "_verify\stderr_$Tag.txt")
$script:t0 = Get-Date

function Wait-Until([int]$ms) {
    $target = $script:t0.AddMilliseconds($ms)
    $left = ($target - (Get-Date)).TotalMilliseconds
    if ($left -gt 0) { Start-Sleep -Milliseconds ([int]$left) }
}

# A=0x41, Z=0x5A, SPACE=0x20, ENTER=0x0D, ESC=0x1B
if ($Mode -eq "multikey") {
    Wait-Until 3000
    "  [harness] t=$([int]((Get-Date)-$script:t0).TotalMilliseconds)ms  A down"
    [Kb]::Down(0x41); Start-Sleep -Milliseconds 120; [Kb]::Up(0x41)
    Wait-Until 4000
    "  [harness] t=$([int]((Get-Date)-$script:t0).TotalMilliseconds)ms  Z down"
    [Kb]::Down(0x5A); Start-Sleep -Milliseconds 120; [Kb]::Up(0x5A)
    Wait-Until 5000
    "  [harness] t=$([int]((Get-Date)-$script:t0).TotalMilliseconds)ms  SPACE down"
    [Kb]::Down(0x20); Start-Sleep -Milliseconds 120; [Kb]::Up(0x20)
    Wait-Until 6000
    "  [harness] t=$([int]((Get-Date)-$script:t0).TotalMilliseconds)ms  ENTER down/up"
    [Kb]::Down(0x0D); Start-Sleep -Milliseconds 120; [Kb]::Up(0x0D)
    Wait-Until 7000
}
elseif ($Mode -eq "heldenter") {
    # one physical press held down ~1.2s (Windows auto-repeat kicks in), then more holds
    Wait-Until 3000
    "  [harness] t=$([int]((Get-Date)-$script:t0).TotalMilliseconds)ms  ENTER held down 1200ms"
    [Kb]::Down(0x0D)
    Start-Sleep -Milliseconds 1200
    [Kb]::Up(0x0D)
    "  [harness] ENTER released"
    Start-Sleep -Milliseconds 500
    "  [harness] ENTER held down 1000ms again"
    [Kb]::Down(0x0D)
    Start-Sleep -Milliseconds 1000
    [Kb]::Up(0x0D)
    "  [harness] ENTER released"
    Start-Sleep -Milliseconds 500
    "  [harness] ENTER held down 800ms again"
    [Kb]::Down(0x0D)
    Start-Sleep -Milliseconds 800
    [Kb]::Up(0x0D)
    "  [harness] ENTER released"
    Wait-Until 9000
}

"  [harness] t=$([int]((Get-Date)-$script:t0).TotalMilliseconds)ms  ESC down/up (exit)"
[Kb]::Down(0x1B); Start-Sleep -Milliseconds 100; [Kb]::Up(0x1B)

$script:py.WaitForExit(10000) | Out-Null
$deadline = (Get-Date).AddSeconds(5)
while (-not $script:py.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200; $script:py.Refresh() }
if (-not $script:py.HasExited) { "  [harness] program did not exit within 15s, killing"; $script:py.Kill() }
else { "  [harness] program exited on its own, exit code = $($script:py.ExitCode)" }

Start-Sleep -Milliseconds 300
"--- program output ($LogFile) ---"
if (Test-Path $log) { Get-Content $log -Encoding UTF8 } else { "(no log file)" }
"--- stderr ---"
$errFile = Join-Path $PWD "_verify\stderr_$Tag.txt"
$err = if (Test-Path $errFile) { Get-Content $errFile -Raw } else { "" }
if ([string]::IsNullOrWhiteSpace($err)) { "(empty)" } else { $err }
