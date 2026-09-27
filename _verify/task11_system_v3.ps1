# Task 11 system-level test, STUCK-PROOF design. Temporary script.
#
# Why this design:
#   The previous single-long-script harness could be interrupted mid-step, leaving the
#   python runner process alive while it still held a note key down. Here every step is a
#   fresh, short-lived process, and the FINALLY block releases all simulated input even if
#   a step throws or the script is stopped. Nothing is ever left held by a killed process.
#
# Safety:
#   - dedicated test window, confirmed foreground; cursor parked inside it
#   - Enter is driven through the real hook callback path (io._hook_callback), NOT keybd_event
#   - real key input only via PlaybackExecutor -> input.py
#   - all state is read read-only via GetAsyncKeyState
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class T11S {
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    public static bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }
    public static void KeyUp(byte vk) { keybd_event(vk, 0, 2, UIntPtr.Zero); }
    public static void MouseUp(uint f) { mouse_event(f, 0, 0, 0, UIntPtr.Zero); }
    public static string Cls(IntPtr h) { StringBuilder s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
}
'@

$SHARP = [string][char]0x2191
$FLAT = [string][char]0x2193
$results = @()

function Check([string]$name, [string]$expected, [string]$actual) {
    $ok = $expected -eq $actual
    $script:results += [pscustomobject]@{ Test = $name; Expected = $expected; Actual = $actual; Pass = $ok }
    "{0}  {1}  expected=[{2}] actual=[{3}]" -f $(if ($ok) { "PASS" } else { "FAIL" }), $name, $expected, $actual
}

# Normalise the runner's "-" placeholder (nothing held) to empty.
function Clean([string]$v) { if ($v -eq "-") { return "" } return $v }

function Run-Once([string]$stepCmd) {
    # One short-lived runner process: initialise, run a single command, print state, exit.
    $SCRIPT = @"
import ctypes, os, sys
sys.path.insert(0, r'$PWD')
import input as io
from harmonica_app import FixedScorePlayer
from score import parse_score_notes
from input import KBDLLHOOKSTRUCT

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
KEY_VKS = {'z':0x5A,'x':0x58,'c':0x43,'v':0x56,'b':0x42,'n':0x4E,'m':0x4D,',':0xBC}
MOUSE_VKS = {'left':0x01,'right':0x02,'middle':0x04}
u = ctypes.WinDLL('user32', use_last_error=True)
keep = {}

def down(vk):
    return bool(u.GetAsyncKeyState(vk) & 0x8000)

def snap():
    k = '+'.join(sorted(n for n,v in KEY_VKS.items() if down(v))) or '-'
    b = '/'.join(sorted(n for n,v in MOUSE_VKS.items() if down(v))) or '-'
    return k, b

def post(vk, msg):
    info = KBDLLHOOKSTRUCT(); info.vkCode = vk; info.scanCode = 0
    info.flags = 0; info.time = 0; info.dwExtraInfo = 0
    keep['i'] = info
    io._hook_callback(0, msg, ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value)

def drain():
    for _ in range(100):
        if io._drain_callbacks(timeout=0.5):
            return
        import time as _t; _t.sleep(0.01)

player = None
def build(text):
    global player
    notes = parse_score_notes(text.replace('|', ' '))
    player = FixedScorePlayer(notes)
    io.set_enter_callbacks(on_down=player.enter_down, on_up=player.enter_up)
    return notes

try:
    build(r'''$score''')
    for raw in r'''$stepCmd'''.split(';'):
        cmd = raw.strip()
        if not cmd:
            continue
        if cmd == 'enter_down':
            post(0x0D, WM_KEYDOWN); drain()
        elif cmd == 'enter_up':
            post(0x0D, WM_KEYUP); drain()
        elif cmd.startswith('enter_down_n'):
            for _ in range(int(cmd.split()[1])):
                post(0x0D, WM_KEYDOWN)
            drain()
        elif cmd.startswith('enter_up_n'):
            for _ in range(int(cmd.split()[1])):
                post(0x0D, WM_KEYUP)
            drain()
        elif cmd == 'shutdown':
            player.shutdown()
    k, b = snap()
    print('STATE|index=%d|finished=%s|keys=%s|mouse=%s' % (player.index, player.is_finished(), k, b))
finally:
    # always release, even if a step above raised
    try:
        player.shutdown()
    except Exception:
        pass
"@
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($SCRIPT)
    $b64 = [Convert]::ToBase64String($bytes)
    $out = & python -c "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode('utf-8'))" $b64 2>&1
    return ($out | Where-Object { $_ -like "STATE|*" } | Select-Object -Last 1)
}

function State-Of([string]$line) {
    if ($line -match 'keys=([^|]*)\|mouse=(.*)$') {
        return (Clean $Matches[1]) + "|" + (Clean $Matches[2].Trim())
    }
    return "PARSE_FAIL"
}
function Index-Of([string]$line) {
    if ($line -match 'index=(\d+)') { return "index=" + $Matches[1] }
    return "index=?"
}

$win = $null
try {
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
    if ($h -eq [IntPtr]::Zero) { throw "test window not created" }
    Start-Sleep -Milliseconds 800
    "test window hwnd=$h class=$([T11S]::Cls($h))"
    "foreground    class=$([T11S]::Cls([T11S]::GetForegroundWindow()))"

    $root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
    $r = $root.Current.BoundingRectangle
    [void][T11S]::SetCursorPos([int]($r.Left + $r.Width / 2), [int]($r.Top + $r.Height / 2))
    Start-Sleep -Milliseconds 300
    "cursor parked in the test window"

    # ---------- A. single note ----------
    "`n=== A. single note ==="
    $line = Run-Once "enter_down"
    Check "A1 Enter DOWN -> Z DOWN" "z|" (State-Of $line)
    $line = Run-Once "enter_down;enter_up"
    Check "A2 Enter UP -> Z UP" "|" (State-Of $line)
    Check "A3 index == 1" "index=1" (Index-Of $line)

    # ---------- B. consecutive notes ----------
    "`n=== B. consecutive 1 2 3 ==="
    $line = Run-Once "enter_down"
    Check "B1 note1 -> Z" "z|" (State-Of $line)
    $line = Run-Once "enter_down;enter_up"
    Check "B2 after UP, X ready" "x|" (State-Of $line)
    $line = Run-Once "enter_down;enter_up;enter_down"
    Check "B3 note2 -> X" "x|" (State-Of $line)
    $line = Run-Once "enter_down(3)"
    if (-not $line) {
        # build the 3-tap sequence explicitly
        $line = Run-Once "enter_down;enter_up;enter_down;enter_up;enter_down"
    }
    Check "B4 note3 -> C" "c|" (State-Of $line)
    $line = Run-Once "enter_down;enter_up;enter_down;enter_up;enter_down;enter_up"
    Check "B5 finished, all released" "|" (State-Of $line)
    Check "B6 index == 3" "index=3" (Index-Of $line)

    # ---------- C. hold Enter (repeated DOWN) ----------
    "`n=== C. hold Enter (repeated DOWN) ==="
    $line = Run-Once "enter_down;enter_down_n 5;enter_down_n 10"
    Check "C1 repeated DOWN during hold: only Z down, index still 0" "z|" (State-Of $line)
    Check "C2 index still 0" "index=0" (Index-Of $line)
    $line = Run-Once "enter_down;enter_down_n 5;enter_up"
    Check "C3 after release: all up" "|" (State-Of $line)

    # ---------- D. tuning ----------
    "`n=== D. tuning $SHARP 3 ==="
    $line = Run-Once "enter_down"
    Check "D1 Enter DOWN -> C + Right DOWN" "c|right" (State-Of $line)
    $line = Run-Once "enter_down;enter_up"
    Check "D2 Enter UP -> all up" "|" (State-Of $line)

    # ---------- E. tuning run ----------
    "`n=== E. tuning run $SHARP 3 4 5 ==="
    $line = Run-Once "enter_down"
    Check "E1 3 -> C+right" "c|right" (State-Of $line)
    $line = Run-Once "enter_down;enter_up"
    Check "E2 after UP -> V+right (right KEPT, no jitter)" "v|right" (State-Of $line)
    $line = Run-Once "enter_down;enter_up;enter_down"
    Check "E3 4 -> V+right" "v|right" (State-Of $line)
    $line = Run-Once "enter_down;enter_up;enter_down;enter_up"
    Check "E4 after UP -> B+right (right still kept)" "b|right" (State-Of $line)
    $line = Run-Once "enter_down;enter_up;enter_down;enter_up;enter_down"
    Check "E5 5 -> B+right" "b|right" (State-Of $line)
    $line = Run-Once "enter_down;enter_up;enter_down;enter_up;enter_down;enter_up"
    Check "E6 range over -> all released" "|" (State-Of $line)

    # ---------- F. mixed score ----------
    "`n=== F. mixed score, note by note ==="
    $mixed = "1|2|[$SHARP|3|4|5]|6|[~|7|1']|[$FLAT|2]"
    $steps = @(
        @(1,  "z|",       "F1  1 normal -> z"),
        @(2,  "x|",       "F2  next 2 ready"),
        @(3,  "x|",       "F3  2 normal -> x"),
        @(4,  "c|right",  "F4  next 3 sharp ready"),
        @(5,  "c|right",  "F5  3 sharp -> c+right"),
        @(6,  "v|right",  "F6  next 4 sharp (right kept)"),
        @(7,  "v|right",  "F7  4 sharp -> v+right"),
        @(8,  "b|right",  "F8  next 5 sharp (right kept)"),
        @(9,  "b|right",  "F9  5 sharp -> b+right"),
        @(10, "n|",       "F10 next 6 normal (right released)"),
        @(11, "n|",       "F11 6 normal -> n"),
        @(12, "m|middle", "F12 next 7 half (middle down)"),
        @(13, "m|middle", "F13 7 half -> m+middle"),
        @(14, ",|middle", "F14 next 1' half (middle kept)"),
        @(15, ",|middle", "F15 1' half -> comma+middle"),
        @(16, "x|left",   "F16 next 2 flat (middle up, left down)"),
        @(17, "x|left",   "F17 2 flat -> x+left"),
        @(18, "|",        "F18 finished, all released")
    )
    $mixedScore = $mixed
    foreach ($s in $steps) {
        $n = $s[0]
        $cmds = @()
        for ($i = 1; $i -le $n; $i++) { $cmds += "enter_down"; if ($i -lt $n) { $cmds += "enter_up" } }
        # include the final enter_up for the fully-finished step
        if ($n -eq 18) { $cmds += "enter_up" }
        $line = Run-OnceWithScore $mixedScore ($cmds -join ";")
        Check $s[2] $s[1] (State-Of $line)
    }

    # ---------- G. after finished ----------
    "`n=== G. after finished ==="
    $all18 = (1..18)
    $cmds18 = @()
    for ($i = 1; $i -le 18; $i++) { $cmds18 += "enter_down"; if ($i -lt 18) { $cmds18 += "enter_up" } }
    $line = Run-OnceWithScore $mixedScore (($cmds18 + "enter_up") -join ";")
    Check "G1 finished state: everything released" "|" (State-Of $line)
    $line = Run-OnceWithScore $mixedScore (($cmds18 + @("enter_up","enter_down","enter_up")) -join ";")
    Check "G2 extra Enter after finish produces no input" "|" (State-Of $line)

    # ---------- I. repeated DOWN / UP ----------
    "`n=== I. repeated DOWN / UP ==="
    $line = Run-OnceWithScore "1|2|3" "enter_down;enter_down_n 4"
    Check "I1 repeated DOWN: only Z down" "z|" (State-Of $line)
    Check "I2 index still 0" "index=0" (Index-Of $line)
    $line = Run-OnceWithScore "1|2|3" "enter_down;enter_down_n 4;enter_up;enter_up_n 4"
    Check "I3 repeated UP: X ready, index 1" "x|" (State-Of $line)
    Check "I4 index == 1" "index=1" (Index-Of $line)
    $line = Run-OnceWithScore "1|2|3" "enter_down;enter_up;enter_up_n 4;enter_down"
    Check "I5 next Enter DOWN plays note 2" "x|" (State-Of $line)
    $line = Run-OnceWithScore "1|2|3" "enter_down;enter_up;enter_up_n 4;enter_down;enter_up"
    Check "I6 after UP, C ready" "c|" (State-Of $line)

    # ---------- H. shutdown releases ----------
    "`n=== H. shutdown while a note is DOWN ==="
    $line = Run-OnceWithScore "[$SHARP|3]|4" "enter_down"
    Check "H1 before shutdown: C+right DOWN" "c|right" (State-Of $line)
    $line = Run-OnceWithScore "[$SHARP|3]|4" "enter_down;shutdown"
    Check "H2 after shutdown: everything released" "|" (State-Of $line)
    $line = Run-OnceWithScore "[$SHARP|3]|4" "enter_down;enter_up;shutdown"
    Check "H3 after note + shutdown: released, index 1" "|" (State-Of $line)
    Check "H4 index == 1" "index=1" (Index-Of $line)
}
finally {
    # STUCK-PROOF: release everything no matter how we leave this block
    foreach ($vk in @(0x0D,0x5A,0x58,0x43,0x56,0x42,0x4E,0x4D,0xBC,0x10,0x11,0x12,0x09,0x20)) { [T11S]::KeyUp([byte]$vk) }
    foreach ($m in @(0x0004,0x0010,0x0040)) { [T11S]::MouseUp($m) }
    Start-Sleep -Milliseconds 200
    if ($win -and -not $win.HasExited) {
        try { $win.CloseMainWindow() | Out-Null } catch {}
        for ($i = 0; $i -lt 8; $i++) { Start-Sleep -Milliseconds 300; $win.Refresh(); if ($win.HasExited) { break } }
        if (-not $win.HasExited) { $win.Kill() }
    }
}
