# Temporary Task 5 test D: the "az" investigation.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KbD {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern IntPtr LoadKeyboardLayoutW(string id, uint flags);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
    public static void Down(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void Up(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Press(byte vk) { Down(vk); System.Threading.Thread.Sleep(60); Up(vk); }
    public static void Chord(byte mod, byte key) { Down(mod); Down(key); System.Threading.Thread.Sleep(60); Up(key); Up(mod); }
    public static string ForceEnglishLayout(IntPtr hwnd) {
        IntPtr hkl = LoadKeyboardLayoutW("00000409", 1);
        bool ok = PostMessageW(hwnd, 0x0050, IntPtr.Zero, hkl);
        return "english layout handed to notepad=" + ok;
    }
}
'@

# ---------- D1: python processes before / after ----------
"`n================ D1: python processes when nothing of ours is running ================"
Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, Path | Format-Table -AutoSize
"python/pwsh leftover count: " + (@(Get-Process python, pythonw -ErrorAction SilentlyContinue).Count)

# ---------- D2: search the project for input-simulation code ----------
"`n================ D2: input-simulation code in the project (excluding _verify) ================"
$hits = Get-ChildItem -Recurse -File |
    Where-Object { $_.FullName -notmatch '\\_verify\\' -and $_.Extension -in '.py', '.json' } |
    Select-String -Pattern 'press_key|release_key|press_mouse|release_mouse|keybd_event|SendInput|keyboard\.Controller|mouse\.Controller'
if ($hits) { $hits | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" } } else { "(no hits)" }
"`nfiles scanned:"
Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '\\_verify\\' -and $_.Extension -in '.py', '.json' } |
    ForEach-Object { "  " + $_.FullName.Replace($PWD.Path + '\', '') }

# ---------- D3 / D4 with a live Notepad ----------
$testFile = Join-Path $PWD ("_verify\task5_d_{0}.txt" -f (Get-Date -Format 'HHmmss'))
Set-Content -Path $testFile -Value "AAA" -NoNewline -Encoding ascii
"`ntest file: $testFile  content=[" + (Get-Content $testFile -Raw) + "]"

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
"notepad pid=$($np.Id) title='$($np.MainWindowTitle)'"
[KbD]::ForceEnglishLayout($h) | Out-Null

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document)
function Get-Editor { return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }
function Get-Buffer { $tp = (Get-Editor).GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern); return $tp.DocumentRange.GetText(-1) }
function Focus-Editor { (Get-Editor).SetFocus(); Start-Sleep -Milliseconds 450 }

"waiting 2s before starting the program..."
Start-Sleep -Seconds 2

$log = Join-Path $PWD "_verify\task5_d_log.txt"
$err = Join-Path $PWD "_verify\task5_d_err.txt"
Remove-Item -Force $log, $err -ErrorAction SilentlyContinue
$env:DSH_ENTER_TEST_AUTOSTART_MS = "0"
$env:DSH_ENTER_TEST_VK_REPORT = ""
$py = Start-Process python -ArgumentList 'main.py' -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput $log -RedirectStandardError $err
Start-Sleep -Milliseconds 1200
"program running: " + (-not $py.HasExited)

# ---------- D3: 5+ seconds idle, keyboard untouched ----------
"`n================ D3: 5s idle with the program running, keyboard untouched ================"
Focus-Editor
$idleBefore = Get-Buffer
"buffer before idle = [$idleBefore]"
$t0 = Get-Date
for ($i = 1; $i -le 5; $i++) {
    Start-Sleep -Seconds 1
    $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
    "  t=$i s  buffer=[" + (Get-Buffer) + "]  focusClass=" + $focused.Current.ClassName
}
$idleAfter = Get-Buffer
"buffer after 5s idle = [$idleAfter]"
"NO CHANGE during idle (no self-generated input): " + ($idleAfter -eq $idleBefore)

# manual-equivalent a and z must still arrive
"`nsending a / z (equivalent to typing them by hand):"
Focus-Editor
[KbD]::Press(0x41); Start-Sleep -Milliseconds 300
[KbD]::Press(0x5A); Start-Sleep -Milliseconds 400
$typed = Get-Buffer
"buffer after a / z = [$typed]"
"a and z arrived normally: " + ($typed -eq "az")

# ---------- exit the program ----------
"`n================ D4: after the program exits ================"
Focus-Editor
[KbD]::Press(0x1B)
$py.WaitForExit(10000) | Out-Null
$py.Refresh()
"program exited on its own: $($py.HasExited)"
if (-not $py.HasExited) { $py.Kill(); "KILLED" }
Start-Sleep -Milliseconds 600

"python/pwsh processes after exit:"
$left = Get-Process python, pythonw -ErrorAction SilentlyContinue
if ($left) { $left | Select-Object Id, ProcessName, Path | Format-Table -AutoSize } else { "  (none)" }

"now typing a / z again to prove the keyboard is untouched after exit:"
[KbD]::Chord(0x11, 0x41); Start-Sleep -Milliseconds 250
[KbD]::Press(0x2E); Start-Sleep -Milliseconds 400
Focus-Editor
[KbD]::Press(0x41); Start-Sleep -Milliseconds 300
[KbD]::Press(0x5A); Start-Sleep -Milliseconds 400
$after = Get-Buffer
"buffer after exit + a / z = [$after]"
"keyboard works normally after exit: " + ($after -eq "az")

"`n--- program stdout ---"
Get-Content $log -Encoding UTF8
"--- program stderr ---"
$e = Get-Content $err -Raw
if ([string]::IsNullOrWhiteSpace($e)) { "(empty)" } else { $e }
"--- disk control file ---"
"content = [" + (Get-Content $testFile -Raw) + "]"

"`n--- closing our notepad (no force kill) ---"
$np.CloseMainWindow() | Out-Null
for ($i = 0; $i -lt 10; $i++) { Start-Sleep -Milliseconds 400; $np.Refresh(); if ($np.HasExited) { break } }
if (-not $np.HasExited) { "sending 'n' (do not save)"; [KbD]::Press(0x4E); Start-Sleep -Milliseconds 1000; $np.Refresh() }
"notepad exited: $($np.HasExited)"
