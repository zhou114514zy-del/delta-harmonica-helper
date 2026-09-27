# Task 11 real system-level test. Temporary script. ASCII-only source (powershell.exe 5.1 reads it as GBK).
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
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    public static void MouseUp(uint flag) { mouse_event(flag, 0, 0, 0, UIntPtr.Zero); }
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

# sharp / flat signs are built at runtime so this file stays pure ASCII
$SHARP = [string][char]0x2191
$FLAT = [string][char]0x2193

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
    # Drain any extra lines first so the runner never blocks on a full stdout pipe
    # (a full pipe would freeze the runner mid-command with a note key still held).
    while ($proc.StandardOutput.Peek() -ne -1) {
        $proc.StandardOutput.ReadLine() | Out-Null
    }
    return $proc.StandardOutput.ReadLine()
}

"runner handshake: " + $proc.StandardOutput.ReadLine()

function State-Of([string]$line) {
    if ($line -match 'keys=\[([^\]]*)\] mouse=\[([^\]]*)\]') {
        # the runner prints "-" for "nothing held"; normalise it to empty
        $k = $Matches[1]; if ($k -eq "-") { $k = "" }
        $m = $Matches[2]; if ($m -eq "-") { $m = "" }
        return $k + "|" + $m
    }
    return "PARSE_FAIL"
}
function Index-Of([string]$line) {
    if ($line -match 'index=(\d+)') { return "index=" + $Matches[1] }
    return "index=?"
}

"`n================ A. single note ================"
"runner: " + (Send-Cmd "score 1")
$line = Send-Cmd "enter_down"
"runner: $line"
Check "A1 Enter DOWN -> Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"
"runner: $line"
Check "A2 Enter UP -> Z UP" "|" (State-Of $line)
Check "A3 index == 1 after UP" "index=1" (Index-Of $line)

"`n================ B. consecutive notes 1 2 3 ================"
"runner: " + (Send-Cmd "score 1|2|3")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "B1 note1 -> Z" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "B2 after UP, X is ready" "x|" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "B3 note2 -> X (no re-press)" "x|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "B4 after UP, C is ready" "c|" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "B5 note3 -> C" "c|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "B6 finished, everything released" "|" (State-Of $line)

"`n================ C. hold Enter (repeated DOWN) ================"
"runner: " + (Send-Cmd "score 1")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "C1 Enter DOWN -> Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_down_n 5"; "runner: $line"
Check "C2 repeated DOWN during hold: state unchanged (Z still DOWN)" "z|" (State-Of $line)
$line = Send-Cmd "enter_down_n 10"; "runner: $line"
Check "C3 10 more repeated DOWNs: still only Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "C4 after release: everything up" "|" (State-Of $line)

"`n================ D. tuning $SHARP 3 ================"
"runner: " + (Send-Cmd "score [$SHARP|3]")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "D1 Enter DOWN -> C + Right DOWN" "c|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "D2 Enter UP -> C + Right all UP" "|" (State-Of $line)

"`n================ E. tuning run $SHARP 3 4 5 ================"
"runner: " + (Send-Cmd "score [$SHARP|3|4|5]")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "E1 3 -> C+right" "c|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "E2 after UP -> V+right (right KEPT, no jitter)" "v|right" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "E3 4 -> V+right" "v|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "E4 after UP -> B+right (right still kept)" "b|right" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "E5 5 -> B+right" "b|right" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "E6 range over -> everything released" "|" (State-Of $line)

"`n================ F. mixed score, note by note ================"
"runner: " + (Send-Cmd "score 1|2|[$SHARP|3|4|5]|6|[~|7|1']|[$FLAT|2]")
$expect = @(
    @("enter_down", "z|",       "F1  1 normal -> z"),
    @("enter_up",   "x|",       "F2  next note 2 ready"),
    @("enter_down", "x|",       "F3  2 normal -> x"),
    @("enter_up",   "c|right",  "F4  next 3 sharp ready (right down)"),
    @("enter_down", "c|right",  "F5  3 sharp -> c+right"),
    @("enter_up",   "v|right",  "F6  next 4 sharp (right kept)"),
    @("enter_down", "v|right",  "F7  4 sharp -> v+right"),
    @("enter_up",   "b|right",  "F8  next 5 sharp (right kept)"),
    @("enter_down", "b|right",  "F9  5 sharp -> b+right"),
    @("enter_up",   "n|",       "F10 next 6 normal (right released)"),
    @("enter_down", "n|",       "F11 6 normal -> n"),
    @("enter_up",   "m|middle", "F12 next 7 half (middle down)"),
    @("enter_down", "m|middle", "F13 7 half -> m+middle"),
    @("enter_up",   ",|middle", "F14 next 1' half (middle kept)"),
    @("enter_down", ",|middle", "F15 1' half -> comma+middle"),
    @("enter_up",   "x|left",   "F16 next 2 flat (middle up, left down)"),
    @("enter_down", "x|left",   "F17 2 flat -> x+left"),
    @("enter_up",   "|",        "F18 finished, everything released")
)
foreach ($e in $expect) {
    $line = Send-Cmd $e[0]
    "runner: $line"
    Check $e[2] $e[1] (State-Of $line)
}

"`n================ G. after the score is finished ================"
$line = Send-Cmd "enter_down"
"runner: $line"
Check "G1 Enter DOWN after finish produces no input" "|" (State-Of $line)
$line = Send-Cmd "enter_up"
"runner: $line"
Check "G2 Enter UP after finish produces no input" "|" (State-Of $line)
"runner: " + (Send-Cmd "info")

"`n================ I. repeated DOWN / UP through the hook ================"
"runner: " + (Send-Cmd "score 1|2|3")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "I1 first DOWN -> Z DOWN" "z|" (State-Of $line)
$line = Send-Cmd "enter_down_n 4"; "runner: $line"
Check "I2 four repeated DOWNs: state unchanged (Z still down)" "z|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "I3 after UP, X ready" "x|" (State-Of $line)
$line = Send-Cmd "enter_up_n 4"; "runner: $line"
Check "I4 four repeated UPs: state unchanged (X still ready)" "x|" (State-Of $line)
$line = Send-Cmd "enter_down"; "runner: $line"
Check "I5 next Enter DOWN plays note 2 correctly" "x|" (State-Of $line)
$line = Send-Cmd "enter_up"; "runner: $line"
Check "I6 after UP, C ready" "c|" (State-Of $line)

"`n================ H. Esc while a note is DOWN ================"
"runner: " + (Send-Cmd "score [$SHARP|3]|4")
$line = Send-Cmd "enter_down"; "runner: $line"
Check "H1 before Esc: C+right DOWN" "c|right" (State-Of $line)
# the esc command prints two lines (callback line + handler line): read both
$proc.StandardInput.WriteLine("esc")
$proc.StandardInput.Flush()
Start-Sleep -Milliseconds 600
$line1 = $proc.StandardOutput.ReadLine()
$line2 = $proc.StandardOutput.ReadLine()
"runner line1: $line1"
"runner line2: $line2"
$escLine = if ($line2 -match 'keys=\[') { $line2 } else { $line1 }
Check "H2 after Esc: everything released (Enter too)" "|" (State-Of $escLine)
Check "H3 after Esc: listener stopped" "listening=False" ($(if ($escLine -match 'listening=(\w+)') { "listening=" + $Matches[1] } else { "listening=?" }))

"`n================ shutdown ================"
$proc.StandardInput.WriteLine("quit")
$proc.StandardInput.Flush()
$proc.StandardInput.Close()
$proc.WaitForExit(8000) | Out-Null
"runner exited: $($proc.HasExited)"
if (-not $proc.HasExited) { $proc.Kill(); "runner killed" }
Start-Sleep -Milliseconds 300

# Safety net: whatever happened above, make sure nothing is left held down.
function Release-Everything {
    foreach ($vk in @(0x0D,0x5A,0x58,0x43,0x56,0x42,0x4E,0x4D,0xBC,0x10,0x11,0x12,0x09,0x20)) {
        [T11]::KeyUp([byte]$vk)
    }
    foreach ($btn in @(0x0004,0x0010,0x0040)) {   # LEFTTUP / RIGHTUP / MIDDLEUP
        [T11]::MouseUp($btn)
    }
    Start-Sleep -Milliseconds 200
}

"--- runner stderr ---"
$errText = $proc.StandardError.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($errText)) { "(empty)" } else { $errText }

$final = @()
Release-Everything
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
