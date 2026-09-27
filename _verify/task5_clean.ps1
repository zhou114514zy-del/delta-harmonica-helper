# Temporary Task 5 clean retest (A, B, C, E, F). Will be deleted after use.
# Design rules (learned from the previous messy run):
#   - never force-kill Notepad; never send Ctrl+S
#   - always set focus into the text editor and ASSERT it before sending keys
#   - all verdicts come from the editor buffer; the file on disk is only a control
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KbC {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern IntPtr LoadKeyboardLayoutW(string id, uint flags);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
    public static void Down(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void Up(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Press(byte vk) { Down(vk); System.Threading.Thread.Sleep(60); Up(vk); }
    public static void Hold(byte vk, int ms) { Down(vk); System.Threading.Thread.Sleep(ms); Up(vk); }
    public static void Chord(byte mod, byte key) { Down(mod); Down(key); System.Threading.Thread.Sleep(60); Up(key); Up(mod); }
    public static string ForceEnglishLayout(IntPtr hwnd) {
        IntPtr hkl = LoadKeyboardLayoutW("00000409", 1);
        bool ok = PostMessageW(hwnd, 0x0050, IntPtr.Zero, hkl);
        return "english layout handed to notepad=" + ok;
    }
}
'@

$testFile = Join-Path $PWD ("_verify\task5_clean_{0}.txt" -f (Get-Date -Format 'HHmmss'))
Set-Content -Path $testFile -Value "AAA" -NoNewline -Encoding ascii
"test file: $testFile"
"disk content at start = [" + (Get-Content $testFile -Raw) + "]  bytes=" + ([System.IO.File]::ReadAllBytes($testFile) -join ',')

$before = @(Get-Process notepad -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Start-Process "shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" -ArgumentList $testFile | Out-Null
$np = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $np = Get-Process -Name Notepad -ErrorAction SilentlyContinue |
          Where-Object { $_.MainWindowHandle -ne 0 -and $before -notcontains $_.Id } | Select-Object -First 1
    if ($np) { break }
}
if (-not $np) { "FATAL: notepad window not found"; exit 1 }
$np.Refresh()
Start-Sleep -Seconds 3
$h = $np.MainWindowHandle
"notepad pid=$($np.Id) hwnd=$h title='$($np.MainWindowTitle)'"
"layout: " + [KbC]::ForceEnglishLayout($h)

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document)
function Get-Editor { return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }
function Get-Buffer { $tp = (Get-Editor).GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern); return $tp.DocumentRange.GetText(-1) }
function Focus-Editor {
    $ed = Get-Editor
    $ed.SetFocus()
    Start-Sleep -Milliseconds 450
    $f = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($f.Current.ClassName -ne "RichEditD2DPT") {
        throw "FOCUS LOST: the focused element is '" + $f.Current.ClassName + "', not the editor. Aborting."
    }
    return $ed
}
function Clear-Buffer {
    Focus-Editor | Out-Null
    [KbC]::Chord(0x11, 0x41)
    Start-Sleep -Milliseconds 300
    [KbC]::Press(0x2E)
    Start-Sleep -Milliseconds 500
    $b = Get-Buffer
    if ($b -ne "") { throw "buffer not empty after clear: [" + $b + "]" }
}
function Codes([string]$s) { return (($s.ToCharArray() | ForEach-Object { [int]$_ }) -join ',') }

"waiting 2s before any keystroke (hands off the keyboard)..."
Start-Sleep -Seconds 2

$log = Join-Path $PWD "_verify\task5_clean_log.txt"
$err = Join-Path $PWD "_verify\task5_clean_err.txt"
Remove-Item -Force $log, $err -ErrorAction SilentlyContinue
$env:DSH_ENTER_TEST_AUTOSTART_MS = "0"
$env:DSH_ENTER_TEST_VK_REPORT = (Join-Path $PWD "_verify\task5_clean_vk.txt")
$py = Start-Process python -ArgumentList 'main.py' -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput $log -RedirectStandardError $err
Start-Sleep -Milliseconds 1200
"hook running: " + (-not $py.HasExited)
"editor present: " + ((Get-Editor) -ne $null)

$results = @()

# ---------------- TEST A: Enter must be swallowed ----------------
"`n=== TEST A: Enter is detected but must NOT reach Notepad ==="
Clear-Buffer
Focus-Editor | Out-Null
[KbC]::Press(0x0D)
Start-Sleep -Milliseconds 900
$a = Get-Buffer
"[A] buffer after Enter = [$a]  codes=$(Codes $a)"
$aOk = ($a -eq "")
"[A] PASS (Enter detected by the hook, no newline in Notepad): $aOk"
$results += "A(Enter blocked): $aOk"

# ---------------- TEST B: a z space TAB ----------------
"`n=== TEST B: a / z / SPACE / TAB must all reach Notepad ==="
Clear-Buffer
Focus-Editor | Out-Null
[KbC]::Press(0x41); Start-Sleep -Milliseconds 300
[KbC]::Press(0x5A); Start-Sleep -Milliseconds 300
[KbC]::Press(0x20); Start-Sleep -Milliseconds 300
[KbC]::Press(0x09); Start-Sleep -Milliseconds 700
$b = Get-Buffer
"[B] buffer = [$b]  codes=$(Codes $b)"
$bOk = ($b -eq "az `t")
"[B] PASS (exactly a, z, space, TAB): $bOk"
$results += "B(other keys pass): $bOk"

# ---------------- TEST C: hold Enter 1s ----------------
"`n=== TEST C: hold Enter ~1s ==="
Clear-Buffer
Focus-Editor | Out-Null
[KbC]::Hold(0x0D, 1000)
Start-Sleep -Milliseconds 900
$c = Get-Buffer
"[C] buffer after 1s hold = [$c]"
$cOk = ($c -eq "")
"[C] PASS (no newline): $cOk"
$results += "C(hold blocked): $cOk"

# ---------------- TEST E: Enter x3 ----------------
"`n=== TEST E: three quick Enter presses ==="
Clear-Buffer
Focus-Editor | Out-Null
for ($i = 1; $i -le 3; $i++) { [KbC]::Press(0x0D); Start-Sleep -Milliseconds 300 }
Start-Sleep -Milliseconds 800
$e = Get-Buffer
"[E] buffer after 3x Enter = [$e]"
$eOk = ($e -eq "")
"[E] PASS (no newlines): $eOk"
$results += "E(3x Enter blocked): $eOk"

# ---------------- TEST F: a / Enter / z / Enter / space / Enter ----------------
"`n=== TEST F: a / ENTER / z / ENTER / SPACE / ENTER ==="
Clear-Buffer
Focus-Editor | Out-Null
[KbC]::Press(0x41); Start-Sleep -Milliseconds 350
[KbC]::Press(0x0D); Start-Sleep -Milliseconds 350
[KbC]::Press(0x5A); Start-Sleep -Milliseconds 350
[KbC]::Press(0x0D); Start-Sleep -Milliseconds 350
[KbC]::Press(0x20); Start-Sleep -Milliseconds 350
[KbC]::Press(0x0D); Start-Sleep -Milliseconds 800
$f = Get-Buffer
"[F] buffer = [$f]  codes=$(Codes $f)"
$fOk = ($f -eq "az ")
"[F] PASS (exactly 'az ', all three Enters blocked): $fOk"
$results += "F(mixed): $fOk"

# ---------------- shutdown ----------------
"`n=== shutdown ==="
Focus-Editor | Out-Null
[KbC]::Press(0x1B)
$py.WaitForExit(10000) | Out-Null
$py.Refresh()
"program exited on its own: $($py.HasExited)"
if (-not $py.HasExited) { $py.Kill(); "KILLED (safety)" }
Start-Sleep -Milliseconds 500

"`n--- program stdout ---"
Get-Content $log -Encoding UTF8
"--- program stderr ---"
$e2 = Get-Content $err -Raw
if ([string]::IsNullOrWhiteSpace($e2)) { "(empty)" } else { $e2 }

"`n--- raw vkCodes seen by the hook ---"
Get-Content (Join-Path $PWD "_verify\task5_clean_vk.txt") -Encoding UTF8

"`n--- disk file control (must still be exactly AAA) ---"
"content = [" + (Get-Content $testFile -Raw) + "]  bytes=" + ([System.IO.File]::ReadAllBytes($testFile) -join ',')

"`n--- closing the Notepad window we started (no force kill) ---"
$closed = $np.CloseMainWindow()
"CloseMainWindow sent: $closed"
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Milliseconds 400
    $np.Refresh()
    if ($np.HasExited) { break }
}
if (-not $np.HasExited) {
    "notepad still open (a save prompt may be showing); sending 'n' for do-not-save"
    Start-Sleep -Milliseconds 500
    [KbC]::Press(0x4E)   # N = do not save
    Start-Sleep -Milliseconds 1000
    $np.Refresh()
}
"notepad exited: $($np.HasExited)"

"`n==================== SUMMARY ===================="
$results
"--- leftover processes ---"
$left = Get-Process python, pythonw -ErrorAction SilentlyContinue
if ($left) { $left | Select-Object Id, ProcessName, Path | Format-Table -AutoSize } else { "python: (none)" }
