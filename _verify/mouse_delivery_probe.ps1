# 探测：合成的鼠标按下是否会到达应用（sink 窗口）？
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class MP {
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Pt p);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Pt p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X; public int Y; }
    public static bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }
    public static string Cls(IntPtr h) { StringBuilder s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    public static string CursorChain() {
        Pt p; GetCursorPos(out p);
        IntPtr h = WindowFromPoint(p);
        return "cursor=(" + p.X + "," + p.Y + ") window=" + Cls(h) + " windowPid=" + h + " root=" + Cls(GetAncestor(h, 2)) + " foreground=" + Cls(GetForegroundWindow());
    }
}
'@

$winLog = Join-Path $PWD "_verify\mouseprobe_win.txt"
Remove-Item -Force $winLog -ErrorAction SilentlyContinue
$win = Start-Process powershell -PassThru -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$PWD\_verify\test_window.ps1","$winLog"
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 500; $win.Refresh(); if ($win.HasExited) { break }; if ($win.MainWindowHandle -ne 0) { $h = $win.MainWindowHandle; break } }
if ($h -eq [IntPtr]::Zero) { "FATAL: no window"; exit 1 }
Start-Sleep -Milliseconds 700
"window hwnd=$h"

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$r = $root.Current.BoundingRectangle
$cx = [int]($r.Left + $r.Width / 2)
$cy = [int]($r.Top + $r.Height / 2)
[void][MP]::SetCursorPos($cx, $cy)
Start-Sleep -Milliseconds 300
"before: " + [MP]::CursorChain()

# 用 pynput 发一次真实左键 down / up（和程序用的是同一条路径）
python -c "from pynput.mouse import Controller, Button; import time; c=Controller(); c.position=($cx,$cy); time.sleep(0.2); c.press(Button.left); time.sleep(0.4); print('state during synthetic press (from python):', bool(__import__('ctypes').windll.user32.GetAsyncKeyState(1) & 0x8000)); c.release(Button.left); time.sleep(0.2); print('state after release:', bool(__import__('ctypes').windll.user32.GetAsyncKeyState(1) & 0x8000))"
Start-Sleep -Milliseconds 600
"after:  " + [MP]::CursorChain()
"left still down? " + [MP]::Down(0x01)
"`n--- sink window log (does it show a mouse event?) ---"
if (Test-Path $winLog) { Get-Content $winLog -Encoding UTF8 } else { "(no log)" }

"`n--- closing test window ---"
try { $win.CloseMainWindow() | Out-Null } catch {}
for ($i = 0; $i -lt 8; $i++) { Start-Sleep -Milliseconds 300; $win.Refresh(); if ($win.HasExited) { break } }
if (-not $win.HasExited) { $win.Kill() }
"done"
