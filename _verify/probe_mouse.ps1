# Temporary probe: is there an empty desktop spot, and does a right click pop a menu?
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public class Pr {
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Pt p);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X; public int Y; public Pt(int x, int y) { X = x; Y = y; } }

    public static string Info(IntPtr h) {
        if (h == IntPtr.Zero) return "<null>";
        StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
        StringBuilder t = new StringBuilder(256); GetWindowText(h, t, 256);
        uint pid; GetWindowThreadProcessId(h, out pid);
        string name = "?";
        try { name = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; } catch {}
        IntPtr root = GetAncestor(h, 2);
        StringBuilder rc = new StringBuilder(256); GetClassName(root, rc, 256);
        return "hwnd=" + h + " class=" + c + " proc=" + name + " title='" + t + "' rootclass=" + rc;
    }

    public static string At(int x, int y) { return "(" + x + "," + y + ") -> " + Info(WindowFromPoint(new Pt(x, y))); }
}
'@

$sw = [Pr]::GetSystemMetrics(0)
$sh = [Pr]::GetSystemMetrics(1)
"screen = ${sw}x${sh}"

"--- probe some candidate points ---"
[Pr]::At(10, 10)
[Pr]::At(400, 300)
[Pr]::At([int]($sw/2), [int]($sh/2))
[Pr]::At($sw - 40, $sh - 120)
[Pr]::At($sw - 40, $sh - 200)
[Pr]::At($sw - 200, $sh - 120)

"--- right click at bottom right desktop spot and see what pops up ---"
$tx = $sw - 40
$ty = $sh - 120
[void][Pr]::SetCursorPos($tx, $ty)
Start-Sleep -Milliseconds 300
"before: " + [Pr]::Info([Pr]::GetForegroundWindow())
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("")
# use pynput through python for a real right down/up
python -c "from pynput.mouse import Controller, Button; import time; c=Controller(); c.position=($tx,$ty); time.sleep(0.3); c.press(Button.right); time.sleep(0.8); c.release(Button.right); time.sleep(0.3); print('right click sent, pos=', c.position)"
Start-Sleep -Milliseconds 600
"after:  " + [Pr]::Info([Pr]::GetForegroundWindow())
"at point: " + [Pr]::At($tx, $ty)

"--- enumerate visible windows now ---"
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class En {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public delegate bool EP(IntPtr h, IntPtr p);
    public static List<string> Vis() {
        List<string> r = new List<string>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            StringBuilder t = new StringBuilder(512); GetWindowText(h, t, 512);
            if (t.Length == 0) return true;
            StringBuilder c = new StringBuilder(256); GetClassName(h, c, 256);
            uint pid; GetWindowThreadProcessId(h, out pid);
            string n = "?";
            try { n = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; } catch {}
            r.Add("class=" + c + " proc=" + n + " title='" + t + "'");
            return true;
        }, IntPtr.Zero);
        return r;
    }
}
'@
[En]::Vis()

# close the menu that we opened
[System.Windows.Forms.SendKeys]::SendWait("{ESC}")
Start-Sleep -Milliseconds 300
"escape sent, foreground now: " + [Pr]::Info([Pr]::GetForegroundWindow())
