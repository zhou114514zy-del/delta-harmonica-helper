# Task 6 test harness (A-F) + system key-state readings. Temporary; deleted after use.
# Safety rules: focus the editor and ASSERT it before every keystroke burst; no Ctrl+S; no force kill.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class K6 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern IntPtr LoadKeyboardLayoutW(string id, uint flags);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
    public static void Down(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void Up(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Press(byte vk) { Down(vk); System.Threading.Thread.Sleep(60); Up(vk); }
    public static void Chord(byte mod, byte key) { Down(mod); Down(key); System.Threading.Thread.Sleep(60); Up(key); Up(mod); }
    public static bool ZDown() { return (GetAsyncKeyState(0x5A) & 0x8000) != 0; }
    public static bool EnterDown() { return (GetAsyncKeyState(0x0D) & 0x8000) != 0; }
    public static string ForceEnglishLayout(IntPtr hwnd) {
        IntPtr hkl = LoadKeyboardLayoutW("00000409", 1);
        bool ok = PostMessageW(hwnd, 0x0050, IntPtr.Zero, hkl);
        return "english layout handed to notepad=" + ok;
    }
}
'@

$testFile = Join-Path $PWD ("_verify\task6_{0}.txt" -f (Get-Date -Format 'HHmmss'))
Set-Content -Path $testFile -Value "" -NoNewline -Encoding ascii

$before = @(Get-Process notepad -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Start-Process "shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" -ArgumentList $testFile | Out-Null
$np = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $np = Get-Process -Name Notepad -ErrorAction SilentlyContinue |
          Where-Object { $_.MainWindowHandle -ne 0 -and $before -notcontains $_.Id } | Select-Object -First 1
    if ($np) { break }
}
if (-not $np) { "FATAL: notepad not found"; exit 1 }
$np.Refresh()
Start-Sleep -Seconds 3
$h = $np.MainWindowHandle
"notepad pid=$($np.Id) hwnd=$h title='$($np.MainWindowTitle)'"
[K6]::ForceEnglishLayout($h) | Out-Null

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document)
function Get-Editor { return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }
function Get-Buffer {
    $ed = Get-Editor
    $tp = $ed.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    return $tp.DocumentRange.GetText(-1)
}
function Focus-Editor {
    $ed = Get-Editor
    $ed.SetFocus()
    Start-Sleep -Milliseconds 450
    $f = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($f.Current.ClassName -ne "RichEditD2DPT") {
        throw ("FOCUS ASSERT FAILED: focused element is '" + $f.Current.ClassName + "'. Aborting so no keystroke lands in an unknown window.")
    }
}
function Clear-Buffer {
    Focus-Editor
    [K6]::Chord(0x11, 0x41)
    Start-Sleep -Milliseconds 300
    [K6]::Press(0x2E)
    Start-Sleep -Milliseconds 450
    $b = Get-Buffer
    if ($b -ne "") { throw "buffer not empty after clear: [$b]" }
}
function Codes([string]$s) { return (($s.ToCharArray() | ForEach-Object { [int]$_ }) -join ',') }

"waiting 2s before starting anything..."
Start-Sleep -Seconds 2

$log = Join-Path $PWD "_verify\task6_log.txt"
$err = Join-Path $PWD "_verify\task6_err.txt"
Remove-Item -Force $log, $err -ErrorAction SilentlyContinue
$env:DSH_ENTER_TEST_AUTOSTART_MS = "0"
$env:DSH_ENTER_TEST_VK_REPORT = ""
$py = Start-Process python -ArgumentList 'main.py' -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput $log -RedirectStandardError $err
Start-Sleep -Milliseconds 1300
"hook running: " + (-not $py.HasExited)

$results = @()

# ================= TEST A: single press =================
"`n=== TEST A: single Enter press/release ==="
Clear-Buffer
Focus-Editor
$tA = Get-Date
[K6]::Down(0x0D); Start-Sleep -Milliseconds 800; [K6]::Up(0x0D)
$holdA = [math]::Round(((Get-Date) - $tA).TotalSeconds, 2)
Start-Sleep -Milliseconds 800
$a = Get-Buffer
"[A] Enter held ~${holdA}s; buffer = [$a]  codes=$(Codes $a)"
$aOk = ($a -eq "z")
"`n[A] PASS (exactly one z): $aOk"
$results += "A(single): $aOk"

# ================= TEST B: long hold =================
"`n=== TEST B: hold Enter ~2s ==="
Clear-Buffer
Focus-Editor
$zDuring = @()
[K6]::Down(0x0D)
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 100
    $zDuring += [K6]::ZDown()
}
[K6]::Up(0x0D)
# 释放是异步的（在回调工作线程上执行），等一下再看，最多 1.5s
$zAfter = $true
$waited = 0
while ($waited -lt 1500) {
    Start-Sleep -Milliseconds 100
    $waited += 100
    if (-not [K6]::ZDown()) { $zAfter = $false; break }
}
Start-Sleep -Milliseconds 500
$b = Get-Buffer
"[B] Enter held ~2s; buffer = [$b]  codes=$(Codes $b)"
"[B] Z system state during hold: " + (($zDuring | ForEach-Object { if ($_) { "DOWN" } else { "up" } }) -join ' ')
"[B] Z system state after release (waited ${waited}ms): " + $(if ($zAfter) { "DOWN" } else { "up" })
$bOk = ($b -eq "z") -and ($zDuring -notcontains $false) -and (-not $zAfter)
"`n[B] PASS (one z, Z held DOWN during hold, Z up after): $bOk"
$results += "B(hold 2s): $bOk"

# ================= TEST C: three presses =================
"`n=== TEST C: three Enter press/release cycles ==="
Clear-Buffer
Focus-Editor
for ($i = 1; $i -le 3; $i++) {
    [K6]::Down(0x0D); Start-Sleep -Milliseconds 350; [K6]::Up(0x0D)
    Start-Sleep -Milliseconds 400
}
Start-Sleep -Milliseconds 800
$c = Get-Buffer
"[C] buffer = [$c]  codes=$(Codes $c)"
$cOk = ($c -eq "zzz")
"`n[C] PASS (exactly zzz): $cOk"
$results += "C(3x): $cOk"

# ================= TEST D: other keys still work =================
"`n=== TEST D: a / z / space must still reach Notepad ==="
Clear-Buffer
Focus-Editor
[K6]::Press(0x41); Start-Sleep -Milliseconds 300
[K6]::Press(0x5A); Start-Sleep -Milliseconds 300
[K6]::Press(0x20); Start-Sleep -Milliseconds 400
Start-Sleep -Milliseconds 500
$d = Get-Buffer
"[D] buffer = [$d]  codes=$(Codes $d)"
$dOk = ($d -eq "az ")
"`n[D] PASS (a and z and space all arrived): $dOk"
$results += "D(other keys): $dOk"

# ================= TEST E / F: Esc while Enter is held =================
"`n=== TEST F: hold Enter, then press Esc (must not leave Z stuck) ==="
Clear-Buffer
Focus-Editor
[K6]::Down(0x0D)
Start-Sleep -Milliseconds 700
$zHeld = [K6]::ZDown()
"Enter held; Z system state = " + $(if ($zHeld) { "DOWN" } else { "up" })
$tF = Get-Date
[K6]::Press(0x1B)
Start-Sleep -Milliseconds 900
$zAfterEsc = [K6]::ZDown()
"after Esc: Z system state = " + $(if ($zAfterEsc) { "DOWN (STUCK!)" } else { "up" })
$py.WaitForExit(8000) | Out-Null
$py.Refresh()
"program exited on its own: $($py.HasExited)"
$fOk = $zHeld -and (-not $zAfterEsc) -and $py.HasExited
"`n[F] PASS (Z was down while held, released on Esc, program exited): $fOk"
$results += "F(esc releases z): $fOk"
if (-not $py.HasExited) { $py.Kill(); "KILLED (safety)" }

Start-Sleep -Milliseconds 400

# ================= program output =================
"`n--- program stdout ---"
$outLines = Get-Content $log -Encoding UTF8
$outLines
"--- program stderr ---"
$e = Get-Content $err -Raw
if ([string]::IsNullOrWhiteSpace($e)) { "(empty)" } else { $e }

$zDownCount = @($outLines | Where-Object { $_ -eq "Z DOWN" }).Count
$zUpCount = @($outLines | Where-Object { $_ -eq "Z UP" }).Count
$enterDownCount = @($outLines | Where-Object { $_ -eq "Enter DOWN" }).Count
$enterUpCount = @($outLines | Where-Object { $_ -eq "Enter UP" }).Count
"`n--- counts ---"
"Enter DOWN=$enterDownCount  Enter UP=$enterUpCount  Z DOWN=$zDownCount  Z UP=$zUpCount"
"every Z DOWN has a matching Z UP: " + ($zDownCount -eq $zUpCount)
"`n--- VK_Z system state at the very end (expect False) ---"
"Z = " + $(if ([K6]::ZDown()) { "DOWN" } else { "up" })

# ================= TEST G: after exit =================
"`n=== TEST G: after the program exited ==="
"python/pythonw processes:"
$left = Get-Process python, pythonw -ErrorAction SilentlyContinue
if ($left) { $left | Select-Object Id, ProcessName, Path | Format-Table -AutoSize } else { "  (none)" }
"notepad processes (ours): $((Get-Process notepad -ErrorAction SilentlyContinue | Measure-Object).Count)"

"`n--- disk control file (must still be empty; we never pressed Ctrl+S) ---"
"content = [" + (Get-Content $testFile -Raw -ErrorAction SilentlyContinue) + "]"

"`n--- closing our notepad (no force kill) ---"
$np.CloseMainWindow() | Out-Null
for ($i = 0; $i -lt 10; $i++) { Start-Sleep -Milliseconds 400; $np.Refresh(); if ($np.HasExited) { break } }
if (-not $np.HasExited) { "sending 'n' (do not save)"; [K6]::Press(0x4E); Start-Sleep -Milliseconds 1000; $np.Refresh() }
"notepad exited: $($np.HasExited)"

"`n==================== SUMMARY ===================="
$results
