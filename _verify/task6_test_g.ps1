# Task 6 test G: keyboard behaves normally after the program exited. Temporary.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class K6G {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern IntPtr LoadKeyboardLayoutW(string id, uint flags);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
    public static void Down(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void Up(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Press(byte vk) { Down(vk); System.Threading.Thread.Sleep(60); Up(vk); }
    public static string ForceEnglishLayout(IntPtr hwnd) {
        IntPtr hkl = LoadKeyboardLayoutW("00000409", 1);
        bool ok = PostMessageW(hwnd, 0x0050, IntPtr.Zero, hkl);
        return "english layout handed to notepad=" + ok;
    }
}
'@

"--- G1: python processes (expect none) ---"
$left = Get-Process python, pythonw -ErrorAction SilentlyContinue
if ($left) { $left | Select-Object Id, ProcessName, Path | Format-Table -AutoSize } else { "  (none)" }

$testFile = Join-Path $PWD ("_verify\task6_g_{0}.txt" -f (Get-Date -Format 'HHmmss'))
Set-Content -Path $testFile -Value "AAA" -NoNewline -Encoding ascii
"--- G2: fresh notepad with [$((Get-Content $testFile -Raw))] (no hook of ours is running) ---"

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
[K6G]::ForceEnglishLayout($np.MainWindowHandle) | Out-Null

$root = [System.Windows.Automation.AutomationElement]::FromHandle($np.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document)
function Get-Editor { return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }
function Get-Buffer {
    $tp = (Get-Editor).GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    return $tp.DocumentRange.GetText(-1)
}
function Focus-Editor {
    (Get-Editor).SetFocus()
    Start-Sleep -Milliseconds 450
    $f = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($f.Current.ClassName -ne "RichEditD2DPT") { throw ("FOCUS ASSERT FAILED: " + $f.Current.ClassName) }
}

Focus-Editor
"buffer baseline = [" + (Get-Buffer) + "]"
"cursor to end (Right arrow x3) then type a, z:"
[K6G]::Press(0x27); Start-Sleep -Milliseconds 150
[K6G]::Press(0x27); Start-Sleep -Milliseconds 150
[K6G]::Press(0x27); Start-Sleep -Milliseconds 250
[K6G]::Press(0x41); Start-Sleep -Milliseconds 250
[K6G]::Press(0x5A); Start-Sleep -Milliseconds 400
$buf = Get-Buffer
"buffer after typing = [$buf]  codes=$(($buf.ToCharArray() | ForEach-Object { [int]$_ }) -join ',')"
"`nG3 keyboard normal after exit (typed 'az' after AAA): " + ($buf -eq "AAAaz")
"G4 arrow keys still work (cursor moved to end): " + ($buf -eq "AAAaz")
"G5 disk control file still exactly AAA: " + ((Get-Content $testFile -Raw) -eq "AAA")

"`n--- closing our notepad ---"
$np.CloseMainWindow() | Out-Null
for ($i = 0; $i -lt 10; $i++) { Start-Sleep -Milliseconds 400; $np.Refresh(); if ($np.HasExited) { break } }
if (-not $np.HasExited) { [K6G]::Press(0x4E); Start-Sleep -Milliseconds 1000; $np.Refresh() }
"notepad exited: $($np.HasExited)"
