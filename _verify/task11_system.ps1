# Task 11 real system-level test. Temporary script.
# Safety:
#   - a dedicated test window is opened and confirmed foreground; the cursor is parked inside it
#   - Enter is driven through the real hook callback path (io._hook_callback), NOT keybd_event
#   - real key input only happens via PlaybackExecutor -> input.py
#   - all state is read read-only via GetAsyncKeyState
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class T11 {
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    public static bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }
    public static void KeyDown(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void KeyUp(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Chord(byte a, byte b) { KeyDown(a); KeyDown(b); System.Threading.Thread.Sleep(60); KeyUp(b); KeyUp(a); }
    public static string Cls(IntPtr h) { StringBuilder s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
}
'@

$results = @()
function Check([string]$name, [string]$expected, [string]$actual) {
    $ok = $expected -eq $actual
    $script:results += [pscustomobject]@{ Test = $name; Expected = $expected; Actual = $actual; Pass = $ok }
    "{0}  {1}  expected=[{2}] actual=[{3}]" -f $(if ($ok) { "PASS" } else { "FAIL" }), $name, $expected, $actual
}

# ---------- dedicated test window ----------
$winLog = Join-Path $PWD "_verify\t11win.txt"
Remove-Item -Force $winLog -ErrorAction SilentlyContinue
$win = Start-Process powershell -PassThru -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$PWD\_verify\test_window.ps1","$winLog"
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $win.Refresh()
    if ($win.HasExited) { break }
    if ($win.MainWindowHandle -ne 0) { $h = $win.MainWindowHandle; break }
}
if ($h -eq [IntPtr]::Zero) { "FATAL: test window not created"; if (-not $win.HasExited) { $win.Kill() }; exit 1 }
Start-Sleep -Milliseconds 800
"test window hwnd=$h class=$([T11]::Cls($h))"
"foreground    class=$([T11]::Cls([T11]::GetForegroundWindow()))"

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$r = $root.Current.BoundingRectangle
$cx = [int]($r.Left + $r.Width / 2)
$cy = [int]($r.Top + $r.Height / 2)
[void][T11]::SetCursorPos($cx, $cy)
Start-Sleep -Milliseconds 400
"cursor parked at ($cx,$cy)"

"opening a context menu with CTRL+U (a later right UP will close it)"
[T11]::Chord(0x11, 0x55)
Start-Sleep -Milliseconds 800

# ---------- protocol runner ----------
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = "_verify\task11_runner.py"
$psi.WorkingDirectory = $PWD.Path
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)

function Send-Cmd([string]$cmd) {
    $proc.StandardInput.WriteLine($cmd)
    $proc.StandardInput.Flush()
    Start-Sleep -Milliseconds 320
    return $proc.StandardOutput.ReadLine()
}

"runner handshake: " + $proc.StandardOutput.ReadLine()

function State-Of([string]$line) {
    # 从运行器输出里抽取 "keys=[...] mouse=[...]" 部分
    if ($line -match 'keys=\[([^\]]*)\] mouse=\[([^\]]*)\]') {
        return $Matches[1] + "|" + $Matches[2]
    }
    return "PARSE_FAIL: $line"
}

"`n================ A. 单音 ================"
"runner: " + (Send-Cmd "score 1")
$line = Send-Cmd "enter_down"
"runner: $line"
Check "A1 Enter DOWN -> Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"
"runner: $line"
Check "A2 Enter UP -> Z UP, index=1" "|" (State-Of $line)
Check "A2b index == 1" "index=1" ($(if ($line -match 'index=(\d+)') { "index=" + $Matches[1] } else { "index=?" }))

"`n================ B. 连续音 1 2 3 ================"
"runner: " + (Send-Cmd "score 1|2|3")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "B1 1 -> Z" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "B2 松开后 X 就绪" "x|" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "B3 2 -> X（不重复按）" "x|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "B4 松开后 C 就绪" "c|" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "B5 3 -> C" "c|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "B6 播完且全部释放" "|" (State-Of $line)

"`n================ C. 长按 Enter（期间多次重复 DOWN） ================"
"runner: " + (Send-Cmd "score 1")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "C1 Enter DOWN -> Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_down_n 5"; "runner: $line"
Check "C2 长按期间重复 DOWN 不改变状态（Z 仍 DOWN，无重复 press）" "z|" (State-Of $line)
$line = Send-Cmd "enter_down_n 10"; "runner: $line"
Check "C3 再重复 10 次仍然只是 Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "C4 松开后释放" "|" (State-Of $line)

"`n================ D. 调音 [↑ 3] ================"
"runner: " + (Send-Cmd "score [↑|3]")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "D1 Enter DOWN -> C + Right DOWN" "c|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "D2 Enter UP -> C + Right 全部 UP" "|" (State-Of $line)

"`n================ E. 调音连续 [↑ 3 4 5] ================"
"runner: " + (Send-Cmd "score [↑|3|4|5]")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "E1 3 -> C+right" "c|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "E2 松开 -> V+right（right 保持，没有抖动）" "v|right" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "E3 4 -> V+right" "v|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "E4 松开 -> B+right（right 仍保持）" "b|right" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "E5 5 -> B+right" "b|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "E6 区间结束 -> 全部释放" "|" (State-Of $line)

"`n================ F. 混合谱（逐个音符） ================"
"runner: " + (Send-Cmd "score 1|2|[↑|3|4|5]|6|[~|7|1']|[↓|2]")
$expect = @(
    @("enter_down", "z|",        "F1  1 normal   z"),
    @("enter_up",   "x|",        "F2  -> 2 就绪"),
    @("enter_down", "x|",        "F3  2 normal   x"),
    @("enter_up",   "c|right",   "F4  -> 3 sharp 就绪 (right 按下)"),
    @("enter_down", "c|right",   "F5  3 sharp    c+right"),
    @("enter_up",   "v|right",   "F6  -> 4 sharp (right 保持)"),
    @("enter_down", "v|right",   "F7  4 sharp    v+right"),
    @("enter_up",   "b|right",   "F8  -> 5 sharp (right 保持)"),
    @("enter_down", "b|right",   "F9  5 sharp    b+right"),
    @("enter_up",   "n|",        "F10 -> 6 normal (right 释放)"),
    @("enter_down", "n|",        "F11 6 normal   n"),
    @("enter_up",   "m|middle",  "F12 -> 7 half (middle 按下)"),
    @("enter_down", "m|middle",  "F13 7 half     m+middle"),
    @("enter_up",   ",|middle",  "F14 -> 1' half (middle 保持)"),
    @("enter_down", ",|middle",  "F15 1' half    comma+middle"),
    @("enter_up",   "x|left",    "F16 -> 2 flat (middle 释放, left 按下)"),
    @("enter_down", "x|left",    "F17 2 flat     x+left"),
    @("enter_up",   "|",         "F18 播完，全部释放")
)
foreach ($e in $expect) {
    $line = Send-Cmd $e[0]
    "runner: $line"
    Check $e[2] $e[1] (State-Of $line)
}

"`n================ G. 播放结束 ================"
$line = Send-Cmd "enter_down"
"runner: $line"
Check "G1 播完后 Enter DOWN 不产生任何输入" "|" (State-Of $line)
$line = Send-Cmd "enter_up"
"runner: $line"
Check "G2 播完后 Enter UP 不产生任何输入" "|" (State-Of $line)
$line = Send-Cmd "info"
"runner: $line"

"`n================ I. 重复 DOWN / UP（真实钩子路径） ================"
"runner: " + (Send-Cmd "score 1|2|3")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "I1 第一次 DOWN -> Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_down_n 4"; "runner: $line"
Check "I2 重复 DOWN 4 次：状态不变（Z 还是 DOWN）" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "I3 松开后 X 就绪" "x|" (State-Of $line)
$line = Send-Cmd "enter_up_n 4"; "runner: $line"
Check "I4 重复 UP 4 次：状态不变（X 仍是就绪）" "x|" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "I5 再按 Enter -> 正常播放下一个音符 X" "x|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "I6 松开 -> C 就绪" "c|" (State-Of $line)

"`n================ H. Esc（当前音符 DOWN 时退出） ================"
"runner: " + (Send-Cmd "score [↑|3]|4")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "H1 Esc 前 C+right 处于 DOWN" "c|right" (State-Of $line)
$line = Send-Cmd "esc"
"runner: $line"
Check "H2 Esc 后全部释放（含 Enter）" "|" (State-Of $line)
Check "H3 Esc 后监听已停止" "listening=False" ($(if ($line -match 'listening=(\w+)') { "listening=" + $Matches[1] } else { "listening=?" }))

"`n================ 收尾 ================"
$proc.StandardInput.WriteLine("quit")
$proc.StandardInput.Flush()
$proc.StandardInput.Close()
$proc.WaitForExit(8000) | Out-Null
"runner exited: $($proc.HasExited)"
if (-not $proc.HasExited) { $proc.Kill() }
Start-Sleep -Milliseconds 300

"--- runner stderr ---"
$errText = $proc.StandardError.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($errText)) { "(empty)" } else { $errText }

# 最终独立复核：11 个键 + Enter 全部必须为 False
$final = @()
foreach ($pair in @(@("Z",0x5A),@("X",0x58),@("C",0x43),@("V",0x56),@("B",0x42),@("N",0x4E),@("M",0x4D),@("Comma",0xBC),@("Left",0x01),@("Middle",0x04),@("Right",0x02),@("Enter",0x0D))) {
    if ([T11]::Down($pair[1])) { $final += $pair[0] }
}
$finalText = if ($final.Count -eq 0) { "all-false" } else { ($final -join ",") }
Check "FINAL 12 keys all up" "all-false" $finalText

"`n================ SUMMARY ================"
$results | Format-Table -AutoSize | Out-String
$failed = @($results | Where-Object { -not $_.Pass })
"total $($results.Count) checks, failed $($failed.Count)"

"`n--- leftover python processes ---"
$p = Get-Process python, pythonw -ErrorAction SilentlyContinue
if ($p) { $p | Select-Object Id, ProcessName | Format-Table -AutoSize } else { "python/pythonw: (none)" }

"`n--- closing test window ---"
try { $win.CloseMainWindow() | Out-Null } catch {}
for ($i = 0; $i -lt 8; $i++) { Start-Sleep -Milliseconds 300; $win.Refresh(); if ($win.HasExited) { break } }
if (-not $win.HasExited) { $win.Kill() }
"test window closed: $($win.HasExited)"
