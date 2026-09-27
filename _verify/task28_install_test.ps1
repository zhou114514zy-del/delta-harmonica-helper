# Task 28 install/uninstall cycle test (ASCII only)
# 1) silent install  2) launch installed EXE  3) silent uninstall while app is running  4) verify cleanup
$ErrorActionPreference = "Continue"
$out = "C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\_verify\task28_cycle_result.txt"
function W($m) { $m | Tee-Object -FilePath $out -Append }

Remove-Item $out -Force -ErrorAction SilentlyContinue

$proj = "C:\Users\16966\Desktop\ds_w\delta-harmonica-helper"
$setup = Join-Path $proj "release\DeltaHarmonicaHelper_Setup.exe"
$dst = "C:\Program Files\Delta Harmonica Helper"
$exe = Join-Path $dst "DeltaHarmonicaHelper.exe"
$un = Join-Path $dst "uninstall.exe"
$pub = Join-Path $env:PUBLIC "Desktop\Delta Harmonica Helper.lnk"
$sm = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Delta Harmonica Helper.lnk"
$reg = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DeltaHarmonicaHelper"

Add-Type -TypeDefinition @'
using System; using System.Collections.Generic; using System.Text; using System.Runtime.InteropServices;
public struct RCZ { public int L, T, R, B; }
public static class W28T {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RCZ r);
  public static string[] ClassesOf(uint pid) {
    var l = new List<string>();
    EnumWindows(delegate(IntPtr h, IntPtr x) {
      uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h)) { var sb = new StringBuilder(256); GetClassName(h, sb, 256); l.Add(sb.ToString()); }
      return true;
    }, IntPtr.Zero);
    return l.ToArray();
  }
  public static string Client(IntPtr h) { RCZ r; GetClientRect(h, out r); return (r.R - r.L) + "x" + (r.B - r.T); }
}
'@

W "================ STEP 1: silent install (over any previous install) ================"
$a = Start-Process -FilePath $setup -ArgumentList "/S" -Wait -PassThru
W ("install exit code = {0}" -f $a.ExitCode)
W ("install dir exists = {0}" -f (Test-Path $dst))
W ("exe exists         = {0}" -f (Test-Path $exe))
W ("_internal exists   = {0}" -f (Test-Path (Join-Path $dst "_internal")))
W ("_internal files    = {0}" -f (Get-ChildItem (Join-Path $dst "_internal") -Recurse -File -ErrorAction SilentlyContinue).Count)
W ("uninstall.exe      = {0}" -f (Test-Path $un))
W ("config.json        = {0}" -f (Test-Path (Join-Path $dst "config.json")))
W ("total files        = {0}" -f (Get-ChildItem $dst -Recurse -File -ErrorAction SilentlyContinue).Count)
W ("user data shipped  = {0} (must be False)" -f (Test-Path (Join-Path $dst "_internal\Scores")))
W ("desktop shortcut   = {0}" -f (Test-Path $pub))
W ("startmenu shortcut = {0}" -f (Test-Path $sm))
W ("uninstall registry = {0}" -f (Test-Path $reg))

W ""
W "================ STEP 2: launch installed EXE (UAC) ================"
Get-Process DeltaHarmonicaHelper -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$b = Start-Process -FilePath $exe -WorkingDirectory $dst -PassThru
W ("started PID = {0}" -f $b.Id)
$deadline = (Get-Date).AddSeconds(30); $title = ""; $cls = @(); $cs = ""
while ((Get-Date) -lt $deadline) {
  $b.Refresh(); if ($b.HasExited) { break }
  if ($b.MainWindowTitle) {
    Start-Sleep -Milliseconds 800
    $title = $b.MainWindowTitle
    $cls = [W28T]::ClassesOf([uint32]$b.Id)
    $cs = [W28T]::Client([IntPtr]$b.MainWindowHandle)
    break
  }
  Start-Sleep -Milliseconds 200
}
W ("title              = '{0}'" -f $title)
W ("visible classes    = {0}" -f ($cls -join ", "))
W ("no ConsoleWindowClass = {0}" -f ($cls -notcontains "ConsoleWindowClass"))
W ("client size        = {0}" -f $cs)
W ("still running      = {0}" -f (-not $b.HasExited))

W ""
W "================ STEP 3: silent uninstall WHILE app is running ================"
$c = Start-Process -FilePath $un -ArgumentList "/S" -Wait -PassThru
W ("uninstaller exit code = {0}" -f $c.ExitCode)
# uninstaller copies itself to %TEMP% and cleans up there; wait for the dir to go away
$deadline = (Get-Date).AddSeconds(45); $gone = $false
while ((Get-Date) -lt $deadline) {
  if (-not (Test-Path $dst)) { $gone = $true; break }
  Start-Sleep -Milliseconds 500
}
Start-Sleep -Seconds 2

W ""
W "================ STEP 4: verify cleanup ================"
W ("install dir removed   = {0}" -f (-not (Test-Path $dst)))
W ("desktop shortcut gone = {0}" -f (-not (Test-Path $pub)))
W ("startmenu shortcut gone = {0}" -f (-not (Test-Path $sm)))
W ("registry key gone     = {0}" -f (-not (Test-Path $reg)))
W ("no running app        = {0}" -f (-not [bool](Get-Process DeltaHarmonicaHelper -ErrorAction SilentlyContinue)))
W ("leftover in dir       = {0}" -f (Test-Path $dst))
if (Test-Path $dst) { W ("  leftover entries: {0}" -f ((Get-ChildItem $dst -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ", ")) }
# 等自删除重试循环跑完（最多 40 秒），再查临时残留
$tdir = Join-Path $env:LOCALAPPDATA "Temp"
$deadline = (Get-Date).AddSeconds(50)
while ((Get-Date) -lt $deadline) {
  $left = @(Get-ChildItem $tdir -Filter "dh_uninstall_*.exe" -ErrorAction SilentlyContinue)
  $cmds = @(Get-ChildItem $tdir -Filter "dh_cleanup_*.cmd" -ErrorAction SilentlyContinue)
  if ($left.Count -eq 0 -and $cmds.Count -eq 0) { break }
  Start-Sleep -Seconds 2
}
W ("temp uninstaller copies left = {0}" -f @(Get-ChildItem $tdir -Filter "dh_uninstall_*.exe" -ErrorAction SilentlyContinue).Count)
W ("temp cleanup scripts left    = {0}" -f @(Get-ChildItem $tdir -Filter "dh_cleanup_*.cmd" -ErrorAction SilentlyContinue).Count)
W ("python/pythonw running       = {0}" -f [bool](Get-Process python, pythonw -ErrorAction SilentlyContinue))
W ""
W "install log   :"
W ((Get-Content "$env:TEMP\DeltaHarmonicaHelper_install.log" -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 6) -join "`n")
W "uninstall log :"
W ((Get-Content "$env:TEMP\DeltaHarmonicaHelper_uninstall.log" -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 12) -join "`n")
W "================ DONE ================"
