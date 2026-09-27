# Temporary final verification for Task 3. Will be deleted after use.
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class Fv {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Pt p);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out Rc r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, IntPtr e);
    public delegate bool EP(IntPtr h, IntPtr p);
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rc { public int L, T, R, B; }

    public static string Cls(IntPtr h) { StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256); return c.ToString(); }

    public static int PopupCount() {
        int n = 0;
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            if (!Cls(h).Contains("PopupWindowSiteBridge")) return true;
            Rc r; GetWindowRect(h, out r);
            if ((r.R - r.L) > 0 && (r.B - r.T) > 0) n++;
            return true;
        }, IntPtr.Zero);
        return n;
    }

    public static string At(int x, int y) { return Cls(WindowFromPoint(new Pt { X = x, Y = y })); }

    public static void ClickAt(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(150);
        mouse_event(0x0002, 0, 0, 0, IntPtr.Zero);
        System.Threading.Thread.Sleep(80);
        mouse_event(0x0004, 0, 0, 0, IntPtr.Zero);
    }
}
'@

$sw = [Fv]::GetSystemMetrics(0)
$sh = [Fv]::GetSystemMetrics(1)
$tx = $sw - 40
$ty = $sh - 120
"screen=${sw}x${sh} target=($tx,$ty)"

"--- clear any context menu left over from probing ---"
for ($i = 0; $i -lt 6; $i++) {
    if ([Fv]::PopupCount() -eq 0) { break }
    [Fv]::ClickAt($tx, $ty)
    Start-Sleep -Milliseconds 500
}
$startPopups = [Fv]::PopupCount()
"popup windows with area BEFORE run: $startPopups"

$py = Start-Process python -ArgumentList 'main.py' -PassThru -RedirectStandardOutput "$PWD\_verify\main_stdout.txt" -RedirectStandardError "$PWD\_verify\main_stderr.txt"

Start-Sleep -Milliseconds 3800
$l = [Fv]::PopupCount()
Start-Sleep -Milliseconds 900
$r = [Fv]::PopupCount()
Start-Sleep -Milliseconds 900
$r2 = [Fv]::PopupCount()

$py.WaitForExit()
$py.Refresh()
"--- main.py exit code: $($py.ExitCode) ---"

"popup count while LEFT button held (t=3.8s): $l   (expect 0: left click opens nothing)"
"popup count while RIGHT button held (t=4.7s): $r  (expect 0: menu appears on release)"
"popup count after RIGHT release     (t=5.6s): $r2  (expect >0: menu is open)"
"RIGHT CLICK VERIFIED: " + ($r2 -gt $startPopups -and $r -eq 0 -and $l -eq 0)
"classAtTarget now: " + [Fv]::At($tx, $ty)
"foreground class now: " + [Fv]::Cls([Fv]::GetForegroundWindow())

"--- close the menu ---"
for ($i = 0; $i -lt 6; $i++) {
    if ([Fv]::PopupCount() -eq 0) { break }
    [Fv]::ClickAt([int]($sw/2), [int]($sh - 60))
    Start-Sleep -Milliseconds 500
}
"popup windows after cleanup: " + [Fv]::PopupCount()

"--- main.py console output ---"
Get-Content "$PWD\_verify\main_stdout.txt" -Encoding UTF8
"--- stderr ---"
$err = Get-Content "$PWD\_verify\main_stderr.txt" -Raw
if ([string]::IsNullOrWhiteSpace($err)) { "(empty)" } else { $err }
