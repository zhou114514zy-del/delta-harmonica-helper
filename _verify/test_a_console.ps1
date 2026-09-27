# Temporary Task 4 test A: real console transcript of the program being typed into.
# Runs inside the console that python will inherit.
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinA {
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);

    public static string Activate() {
        IntPtr h = GetConsoleWindow();
        uint my = GetCurrentThreadId();
        uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
        uint tg = GetWindowThreadProcessId(h, IntPtr.Zero);
        AttachThreadInput(my, fg, true);
        AttachThreadInput(my, tg, true);
        ShowWindow(h, 9);
        SetForegroundWindow(h);
        bool ok = GetForegroundWindow() == h;
        AttachThreadInput(my, fg, false);
        AttachThreadInput(my, tg, false);
        StringBuilder c = new StringBuilder(256); GetClassName(GetForegroundWindow(), c, 256);
        return "consoleHwnd=" + h + " foreground=" + GetForegroundWindow() + " ok=" + ok + " fgClass=" + c;
    }
}
'@

$transcript = Join-Path $PWD "_verify\console_transcript.txt"
Remove-Item -Force $transcript -ErrorAction SilentlyContinue
$pidFile = Join-Path $PWD "_verify\python_pid.txt"
Remove-Item -Force $pidFile -ErrorAction SilentlyContinue

Start-Transcript -Path $transcript | Out-Null
$py = Start-Process python -ArgumentList 'main.py' -PassThru -NoNewWindow
Set-Content -Path $pidFile -Value $py.Id

Start-Sleep -Milliseconds 1500
for ($i = 0; $i -lt 12; $i++) {
    $r = [WinA]::Activate()
    if ($r -match "ok=True") { break }
    Start-Sleep -Milliseconds 400
}
"OUTER: activate result -> $r"

Start-Sleep -Milliseconds 700
"[OUTER] sending ENTER down/up into the console"
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds 1200
"[OUTER] sending ENTER down/up again"
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds 1200
"[OUTER] sending ESC to exit"
[System.Windows.Forms.SendKeys]::SendWait("{ESC}")

$py.WaitForExit(12000) | Out-Null
$py.Refresh()
"[OUTER] python HasExited=$($py.HasExited)"
if (-not $py.HasExited) { $py.Kill(); "[OUTER] killed" }
Start-Sleep -Milliseconds 500
Stop-Transcript | Out-Null
