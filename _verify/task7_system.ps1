# Task 7 真实系统级测试：鼠标键 + Z 组合（测试 B/C/D/G）。临时脚本。
# 安全措施：
#   1) 鼠标按键只发往"专用测试窗口"内部，发之前用 WindowFromPoint 校验该点属于测试窗口
#   2) 发按键前把焦点明确设到测试窗口
#   3) 用只读 GetAsyncKeyState 验证"是否真的按住"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class T7 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Pt p);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Pt p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out Rc r);
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rc { public int L, T, R, B; }
    public static void KeyDown(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void KeyUp(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Press(byte vk) { KeyDown(vk); System.Threading.Thread.Sleep(60); KeyUp(vk); }
    public static bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }
    public static bool ZDown() { return Down(0x5A); }
    public static bool EnterDown() { return Down(0x0D); }
    public static bool LeftDown() { return Down(0x01); }
    public static bool RightDown() { return Down(0x02); }
    public static bool MiddleDown() { return Down(0x04); }
    public static string Cls(IntPtr h) { StringBuilder s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    public static string CursorClass() { Pt p; GetCursorPos(out p); return Cls(WindowFromPoint(p)); }
    public static string RectOf(IntPtr h) { Rc r; GetWindowRect(h, out r); return "(" + r.L + "," + r.T + ")-(" + r.R + "," + r.B + ")"; }
}
'@

function Get-MouseState([string]$mode) {
    if ($mode -eq "left")   { return [T7]::LeftDown() }
    if ($mode -eq "middle") { return [T7]::MiddleDown() }
    return [T7]::RightDown()
}
function Read-Log([string]$path) {
    if (Test-Path $path) { return ((Get-Content $path -Encoding UTF8) -join " | ") }
    return "(no log)"
}

$modes = @("left", "middle", "right")
$summary = @()

foreach ($mode in $modes) {
    $winLog = Join-Path $PWD "_verify\t7win_$mode.txt"
    Remove-Item -Force $winLog -ErrorAction SilentlyContinue
    "`n################ MODE: $mode ################"

    $win = Start-Process powershell -PassThru -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$PWD\_verify\test_window.ps1","$winLog"
    $h = [IntPtr]::Zero
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        $win.Refresh()
        if ($win.HasExited) { break }
        if ($win.MainWindowHandle -ne 0) { $h = $win.MainWindowHandle; break }
    }
    if ($h -eq [IntPtr]::Zero) { "FATAL: test window not created (hasExited=$($win.HasExited))"; if (-not $win.HasExited) { $win.Kill() }; continue }
    Start-Sleep -Milliseconds 700
    $winCls = [T7]::Cls($h)
    "test window hwnd=$h class=$winCls rect=$([T7]::RectOf($h))"

    $root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
    $r = $root.Current.BoundingRectangle
    $cx = [int]($r.Left + $r.Width / 2)
    $cy = [int]($r.Top + $r.Height / 2)
    [void][T7]::SetCursorPos($cx, $cy)
    Start-Sleep -Milliseconds 300
    $under = [T7]::CursorClass()
    "cursor parked at ($cx,$cy); window under cursor = $under (expect $winCls)"

    $log = Join-Path $PWD "_verify\t7log_$mode.txt"
    $err = Join-Path $PWD "_verify\t7err_$mode.txt"
    Remove-Item -Force $log, $err -ErrorAction SilentlyContinue
    $env:DSH_HARMONICA_TEST_MODE = $mode
    $env:DSH_ENTER_TEST_AUTOSTART_MS = "0"
    $env:DSH_ENTER_TEST_VK_REPORT = ""
    $py = Start-Process python -ArgumentList 'main.py' -PassThru -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err
    Start-Sleep -Milliseconds 1300
    "program running: $(-not $py.HasExited)"
    "startup output: " + ((Get-Content $log -Encoding UTF8 | Select-Object -First 4) -join " | ")

    $root.SetFocus()
    Start-Sleep -Milliseconds 400

    if ($mode -eq "right") {
        "sending CTRL+U (context menu), so the right-button UP closes it and it never opens later"
        [T7]::KeyDown(0x11); [T7]::Press(0x55); [T7]::KeyUp(0x11)
        Start-Sleep -Milliseconds 800
        "foreground class after ctrl+u = " + [T7]::Cls([T7]::GetForegroundWindow())
    }

    "sending ENTER down, holding ~1s"
    [T7]::KeyDown(0x0D)
    $samples = @()
    $allDown = $true
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 100
        $z = [T7]::ZDown()
        $m = Get-MouseState $mode
        $samples += "Z=$(if ($z) {'D'} else {'u'})/${mode}=$(if ($m) {'D'} else {'u'})"
        if (-not ($z -and $m)) { $allDown = $false }
    }
    "hold samples: " + ($samples -join ' ')

    "sending ENTER up"
    [T7]::KeyUp(0x0D)
    $waited = 0
    $released = $false
    while ($waited -lt 1500) {
        Start-Sleep -Milliseconds 100
        $waited += 100
        if ((-not [T7]::ZDown()) -and (-not (Get-MouseState $mode))) { $released = $true; break }
    }
    "after release (waited ${waited}ms): Z=$([T7]::ZDown()) ${mode}=$(Get-MouseState $mode)  (both false = released)"
    "test window received: " + (Read-Log $winLog)

    "`n--- G: hold ENTER then press ESC (release_all must clean up) ---"
    $root.SetFocus()
    Start-Sleep -Milliseconds 300
    [T7]::KeyDown(0x0D)
    Start-Sleep -Milliseconds 800
    $gZ = [T7]::ZDown()
    $gM = Get-MouseState $mode
    "before Esc: Z=$gZ  ${mode}=$gM   (both should be True)"
    [T7]::Press(0x1B)
    Start-Sleep -Milliseconds 1000
    $gZ2 = [T7]::ZDown()
    $gM2 = Get-MouseState $mode
    "after Esc:  Z=$gZ2  ${mode}=$gM2   (both should be False)"
    $py.WaitForExit(8000) | Out-Null
    $py.Refresh()
    "program exited on its own: $($py.HasExited)"
    if (-not $py.HasExited) { $py.Kill(); "KILLED (safety)" }
    Start-Sleep -Milliseconds 400

    "--- program output (full) ---"
    Get-Content $log -Encoding UTF8
    "--- program stderr ---"
    $e = Get-Content $err -Raw
    if ([string]::IsNullOrWhiteSpace($e)) { "(empty)" } else { $e }

    $ok = $allDown -and $released -and (-not $gZ2) -and (-not $gM2) -and $py.HasExited
    $summary += "$mode : hold=$allDown release=$released escCleanup=$((-not $gZ2) -and (-not $gM2)) exited=$($py.HasExited) => PASS=$ok"

    try { $win.CloseMainWindow() | Out-Null } catch {}
    for ($i = 0; $i -lt 8; $i++) { Start-Sleep -Milliseconds 300; $win.Refresh(); if ($win.HasExited) { break } }
    if (-not $win.HasExited) { $win.Kill() }
    Start-Sleep -Milliseconds 300
}

"`n==================== SUMMARY ===================="
$summary
"`n--- leftover python processes ---"
$p = Get-Process python, pythonw -ErrorAction SilentlyContinue
if ($p) { $p | Select-Object Id, ProcessName | Format-Table -AutoSize } else { "python/pythonw: (none)" }
"`n--- final key states (all should be False) ---"
"Enter=$([T7]::EnterDown())  Z=$([T7]::ZDown())  Left=$([T7]::LeftDown())  Middle=$([T7]::MiddleDown())  Right=$([T7]::RightDown())"
