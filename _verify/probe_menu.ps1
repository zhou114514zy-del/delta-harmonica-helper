# Temporary probe: what exactly is the XamlExplorerHostIslandWindow, and can it be closed?
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class Wp {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Pt p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out Rc r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int idx);
    public delegate bool EP(IntPtr h, IntPtr p);
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rc { public int L, T, R, B; }

    public static string Desc(IntPtr h) {
        StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
        StringBuilder t = new StringBuilder(256); GetWindowText(h, t, 256);
        Rc r; GetWindowRect(h, out r);
        uint pid; GetWindowThreadProcessId(h, out pid);
        string n = "?"; try { n = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; } catch {}
        return "hwnd=" + h + " proc=" + n + " class=" + c + " title='" + t + "' rect=(" + r.L + "," + r.T + ")-(" + r.R + "," + r.B + ") size=" + (r.R - r.L) + "x" + (r.B - r.T) + " owner=" + GetWindow(h, 4) + " style=0x" + GetWindowLong(h, -16).ToString("X8") + " exstyle=0x" + GetWindowLong(h, -20).ToString("X8");
    }

    public static List<string> All() {
        List<string> r = new List<string>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
            if (c.ToString().Contains("XamlExplorerHostIslandWindow") || c.ToString().Contains("#32768") || c.ToString().Contains("PopupWindowSiteBridge") || c.ToString().Contains("Progman") || c.ToString().Contains("SysListView32"))
                r.Add(Desc(h));
            return true;
        }, IntPtr.Zero);
        return r;
    }

    public static List<IntPtr> ByClass(string frag) {
        List<IntPtr> r = new List<IntPtr>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
            if (c.ToString().Contains(frag)) r.Add(h);
            return true;
        }, IntPtr.Zero);
        return r;
    }
}
'@

"--- interesting windows now ---"
[Wp]::All()

$sw = [Wp]::GetSystemMetrics(0)
$sh = [Wp]::GetSystemMetrics(1)
$tx = $sw - 40
$ty = $sh - 120
"target=($tx,$ty)"

"--- send WM_CLOSE to each XamlExplorerHostIslandWindow ---"
foreach ($h in [Wp]::ByClass("XamlExplorerHostIslandWindow")) {
    "closing " + [Wp]::Desc($h)
    [void][Wp]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
}
Start-Sleep -Milliseconds 800
"--- after WM_CLOSE ---"
[Wp]::All()

