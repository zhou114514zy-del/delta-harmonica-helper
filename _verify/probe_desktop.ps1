# Temporary diagnostic script.
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class W {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int max);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public delegate bool EnumProc(IntPtr h, IntPtr p);

    public static List<string> Visible() {
        List<string> r = new List<string>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            StringBuilder t = new StringBuilder(512);
            GetWindowText(h, t, 512);
            if (t.Length == 0) return true;
            StringBuilder c = new StringBuilder(256);
            GetClassName(h, c, 256);
            uint pid;
            GetWindowThreadProcessId(h, out pid);
            string name = "?";
            try { name = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; } catch {}
            r.Add("pid=" + pid + " proc=" + name + " class=" + c.ToString() + " title=" + t.ToString());
            return true;
        }, IntPtr.Zero);
        return r;
    }
}
'@

"--- visible top-level windows ---"
[W]::Visible()

"--- notepad processes ---"
Get-Process -Name notepad -ErrorAction SilentlyContinue | Select-Object Id, MainWindowHandle, MainWindowTitle | Format-Table -AutoSize | Out-String

"--- store notepad package ---"
Get-AppxPackage -Name "*Notepad*" -ErrorAction SilentlyContinue | Select-Object Name, Version, Status | Format-Table -AutoSize | Out-String

"--- try shell:AppsFolder launch ---"
try {
    Start-Process "shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" -ErrorAction Stop
    "launch command accepted"
} catch {
    "launch failed: " + $_.Exception.Message
}
Start-Sleep -Seconds 8
"--- windows after launch ---"
[W]::Visible()
"--- notepad processes after launch ---"
Get-Process -Name notepad -ErrorAction SilentlyContinue | Select-Object Id, MainWindowHandle, MainWindowTitle | Format-Table -AutoSize | Out-String
