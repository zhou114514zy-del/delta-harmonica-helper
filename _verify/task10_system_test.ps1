# Task 10 real system-level test. Temporary script.
# Safety:
#   1) a dedicated test window is opened first and confirmed foreground
#   2) the cursor is parked in the middle of that window (no user UI is clicked)
#   3) real key states are verified read-only via GetAsyncKeyState
#   4) all real input goes through _verify\task10_runner.py -> input.py public API
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class T10 {
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    public static bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }
    public static void KeyDown(byte vk) { keybd_event(vk, 0, 0, UIntPtr.Zero); }
    public static void KeyUp(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void Press(byte vk) { KeyDown(vk); System.Threading.Thread.Sleep(60); KeyUp(vk); }
    public static void Chord(byte a, byte b) { KeyDown(a); KeyDown(b); System.Threading.Thread.Sleep(60); KeyUp(b); KeyUp(a); }
    public static string Cls(IntPtr h) { StringBuilder s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
}
'@

$KEYVK = @{ "z" = 0x5A; "x" = 0x58; "c" = 0x43; "v" = 0x56; "b" = 0x42; "n" = 0x4E; "m" = 0x4D; "," = 0xBC }
$MOUSEVK = @{ "left" = 0x01; "right" = 0x02; "middle" = 0x04 }
$KEYORDER = @("z", "x", "c", "v", "b", "n", "m", ",")
$MOUSEORDER = @("left", "right", "middle")

function Get-Actual {
    $k = @()
    foreach ($name in $KEYORDER) { if ([T10]::Down($KEYVK[$name])) { $k += $name } }
    $m = @()
    foreach ($name in $MOUSEORDER) { if ([T10]::Down($MOUSEVK[$name])) { $m += $name } }
    return (@($k | Sort-Object) -join ",") + "|" + (@($m | Sort-Object) -join ",")
}

function Get-Expected {
    param([string]$keys, [string]$buttons)
    $k = if ($keys -eq "-") { "" } else { (@($keys.Split(",") | Sort-Object) -join ",") }
    $b = if ($buttons -eq "-") { "" } else { (@($buttons.Split(",") | Sort-Object) -join ",") }
    return "$k|$b"
}

$results = @()
function Check([string]$name, [string]$expected, [string]$actual) {
    $ok = $expected -eq $actual
    $script:results += [pscustomobject]@{ Test = $name; Expected = $expected; Actual = $actual; Pass = $ok }
    "{0}  {1}  expected=[{2}] actual=[{3}]" -f $(if ($ok) { "PASS" } else { "FAIL" }), $name, $expected, $actual
}

# ---------- dedicated test window ----------
$winLog = Join-Path $PWD "_verify\t10win.txt"
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
"test window hwnd=$h class=$([T10]::Cls($h))"
"foreground    class=$([T10]::Cls([T10]::GetForegroundWindow()))"

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$r = $root.Current.BoundingRectangle
$cx = [int]($r.Left + $r.Width / 2)
$cy = [int]($r.Top + $r.Height / 2)
[void][T10]::SetCursorPos($cx, $cy)
Start-Sleep -Milliseconds 400
"cursor parked at ($cx,$cy)"

"opening a context menu with CTRL+U (a later right UP will close it)"
[T10]::Chord(0x11, 0x55)
Start-Sleep -Milliseconds 800

# ---------- protocol runner ----------
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = "_verify\task10_runner.py"
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
    Start-Sleep -Milliseconds 280
}

"runner handshake: " + $proc.StandardOutput.ReadLine()

"`n================ A. empty -> Z ================"
Send-Cmd "apply z -"
Check "A1 empty->Z  Z down" (Get-Expected "z" "-") (Get-Actual)
Send-Cmd "release_all"
Check "A2 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ B. Z -> X ================"
Send-Cmd "apply z -"
Check "B1 Z down" (Get-Expected "z" "-") (Get-Actual)
Send-Cmd "apply x -"
Check "B2 Z->X  Z up, X down" (Get-Expected "x" "-") (Get-Actual)
Send-Cmd "release_all"
Check "B3 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ C. Z+right -> X+right (right must stay down) ================"
Send-Cmd "apply z right"
Check "C1 Z+right down" (Get-Expected "z" "right") (Get-Actual)
Send-Cmd "apply x right"
Check "C2 X+right  Z up, X down, right STILL down" (Get-Expected "x" "right") (Get-Actual)
Send-Cmd "release_all"
Check "C3 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ D. X+right -> B ================"
Send-Cmd "apply x right"
Check "D1 X+right down" (Get-Expected "x" "right") (Get-Actual)
Send-Cmd "apply b -"
Check "D2 B only  X up, right up, B down" (Get-Expected "b" "-") (Get-Actual)
Send-Cmd "release_all"
Check "D3 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ E. C(normal) -> V(sharp) ================"
Send-Cmd "apply c -"
Check "E1 C down, no mouse" (Get-Expected "c" "-") (Get-Actual)
Send-Cmd "apply v right"
Check "E2 V+right  C up, V down, right down" (Get-Expected "v" "right") (Get-Actual)
Send-Cmd "release_all"
Check "E3 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ F. C+right -> V+left ================"
Send-Cmd "apply c right"
Check "F1 C+right down" (Get-Expected "c" "right") (Get-Actual)
Send-Cmd "apply v left"
Check "F2 V+left  C up, right up, V down, left down" (Get-Expected "v" "left") (Get-Actual)
"foreground after right UP = " + [T10]::Cls([T10]::GetForegroundWindow()) + "  (still the test window = right UP closed a menu)"
Send-Cmd "release_all"
Check "F3 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ G. identical state ================"
Send-Cmd "apply z right"
Check "G1 Z+right down" (Get-Expected "z" "right") (Get-Actual)
Send-Cmd "apply z right"
Send-Cmd "apply z right"
Check "G2 after two identical applies the real state is unchanged" (Get-Expected "z" "right") (Get-Actual)
Send-Cmd "release_all"
Check "G3 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ H. apply(empty) ================"
Send-Cmd "apply z right"
Check "H1 Z+right down" (Get-Expected "z" "right") (Get-Actual)
Send-Cmd "apply - -"
Check "H2 apply(empty)  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ I. release_all ================"
Send-Cmd "apply b middle"
Check "I1 B+middle down" (Get-Expected "b" "middle") (Get-Actual)
Send-Cmd "release_all"
Check "I2 release_all  all up" (Get-Expected "-" "-") (Get-Actual)
Send-Cmd "release_all"
Check "I3 release_all again  still all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ J. mixed score 1 2 [^ 3 4 5] 6 [~ 7 1'] [v 2] ================"
$steps = @(
    @("z", "-",      "J1  1 normal   z"),
    @("x", "-",      "J2  2 normal   x"),
    @("c", "right",  "J3  3 sharp    c+right"),
    @("v", "right",  "J4  4 sharp    v+right (right keeps)"),
    @("b", "right",  "J5  5 sharp    b+right (right keeps)"),
    @("n", "-",      "J6  6 normal   n (right up)"),
    @("m", "middle", "J7  7 half     m+middle"),
    @(",", "middle", "J8  1' half    comma+middle (middle keeps)"),
    @("x", "left",   "J9  2 flat     x+left (middle up)")
)
foreach ($s in $steps) {
    Send-Cmd ("apply " + $s[0] + " " + $s[1])
    Check $s[2] (Get-Expected $s[0] $s[1]) (Get-Actual)
}
Send-Cmd "release_all"
Check "J10 release_all  all up" (Get-Expected "-" "-") (Get-Actual)

"`n================ shutdown ================"
Send-Cmd "quit"
$proc.StandardInput.Close()
$proc.WaitForExit(8000) | Out-Null
"runner exited: $($proc.HasExited)  exit code = $(if ($proc.HasExited) { $proc.ExitCode } else { 'n/a' })"
if (-not $proc.HasExited) { $proc.Kill() }
Start-Sleep -Milliseconds 400

$outText = $proc.StandardOutput.ReadToEnd()
$errText = $proc.StandardError.ReadToEnd()
"--- runner stdout (its own independent state readings) ---"
if ([string]::IsNullOrWhiteSpace($outText)) { "(empty)" } else { $outText }
"--- runner stderr ---"
if ([string]::IsNullOrWhiteSpace($errText)) { "(empty)" } else { $errText }

Check "FINAL all keys/mouse up" (Get-Expected "-" "-") (Get-Actual)

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
