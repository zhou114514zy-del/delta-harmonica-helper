# Temporary Task 4 test B (v2): ground truth = the file on disk, not UIA text.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KbB2 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    public static void Down(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void Up(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
}
'@

$testFile = Join-Path $PWD "_verify\notepad_enter_test.txt"
Set-Content -Path $testFile -Value "AAA" -NoNewline -Encoding UTF8
"test file prepared: $testFile  content=[" + (Get-Content $testFile -Raw) + "]"

Start-Process "shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" -ArgumentList $testFile | Out-Null
$np = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $np = Get-Process -Name Notepad -ErrorAction SilentlyContinue |
          Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($np) { break }
}
if (-not $np) { "FATAL: notepad not found"; exit 1 }
$np.Refresh()
Start-Sleep -Seconds 3
"notepad pid=$($np.Id) title='$($np.MainWindowTitle)'"

$root = [System.Windows.Automation.AutomationElement]::FromHandle($np.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document)
$ed = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
"editor class=" + $ed.Current.ClassName

# start listener in the background
$log = Join-Path $PWD "_verify\log_B2.txt"
Remove-Item -Force $log -ErrorAction SilentlyContinue
$env:DSH_ENTER_TEST_AUTOSTART_MS = "0"
$py = Start-Process python -ArgumentList 'main.py' -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput $log -RedirectStandardError (Join-Path $PWD "_verify\stderr_B2.txt")
Start-Sleep -Milliseconds 1500
$ed.SetFocus()
Start-Sleep -Milliseconds 800
"focused class = " + ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.ClassName) + "  (RichEditD2DPT = Notepad has focus)"

# baseline: save once, then read the file from disk
[KbB2]::Down(0x11); [KbB2]::Down(0x53); Start-Sleep -Milliseconds 100; [KbB2]::Up(0x53); [KbB2]::Up(0x11)
Start-Sleep -Milliseconds 1200
$before = Get-Content $testFile -Raw
"file BEFORE Enter: [" + $before + "]  length=" + $before.Length

# three real Enter presses while Notepad owns the focus
for ($i = 1; $i -le 3; $i++) {
    "  sending ENTER #$i (listener runs as a background process)"
    [KbB2]::Down(0x0D); Start-Sleep -Milliseconds 100; [KbB2]::Up(0x0D)
    Start-Sleep -Milliseconds 800
}
Start-Sleep -Milliseconds 500

[KbB2]::Down(0x11); [KbB2]::Down(0x53); Start-Sleep -Milliseconds 100; [KbB2]::Up(0x53); [KbB2]::Up(0x11)
Start-Sleep -Milliseconds 1500
$after = Get-Content $testFile -Raw
"file AFTER 3x Enter: [" + $after + "]  length=" + $after.Length
"line count AFTER: " + (Get-Content $testFile).Count
"NOTEPAD STILL RECEIVED ENTER (file grew): " + ($after.Length -gt $before.Length)

"--- ESC stops the background listener ---"
[KbB2]::Down(0x1B); Start-Sleep -Milliseconds 80; [KbB2]::Up(0x1B)
$py.WaitForExit(12000) | Out-Null
$py.Refresh()
"listener exited on its own: $($py.HasExited)"
if (-not $py.HasExited) { $py.Kill(); "killed" }
Start-Sleep -Milliseconds 300

"--- listener output ---"
Get-Content $log -Encoding UTF8
"--- stderr ---"
$e = Get-Content (Join-Path $PWD "_verify\stderr_B2.txt") -Raw
if ([string]::IsNullOrWhiteSpace($e)) { "(empty)" } else { $e }

Stop-Process -Id $np.Id -Force -ErrorAction SilentlyContinue
"notepad closed"
