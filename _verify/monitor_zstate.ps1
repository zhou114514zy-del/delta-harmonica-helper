# 只读监视脚本：只调用 GetAsyncKeyState 读取 Enter / Z 的系统状态，不注入任何输入。
# 用法：先启动监视，然后手动按住 Enter 约 2.5 秒再松开，最后按 Esc 退出被监视的程序。
# 结果写入 _verify\zustate.txt
$out = Join-Path $PWD "_verify\zustate.txt"
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class ZMon {
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    public static bool Down(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }
}
'@

$lines = @()
$lines += "Z/Enter key state monitor (READ ONLY - no input is injected)"
$lines += "started: $(Get-Date -Format 'HH:mm:ss.fff')"
$t0 = Get-Date
$enterSawDown = $false
$enterReleased = $false
$zDuringHold = @()
$zAfterRelease = $null

for ($i = 0; $i -lt 700; $i++) {          # 最多 70 秒
    $enter = [ZMon]::Down(0x0D)           # VK_RETURN
    $z = [ZMon]::Down(0x5A)               # VK_Z
    $t = [math]::Round(((Get-Date) - $t0).TotalSeconds, 2)

    if ($enter -and -not $enterSawDown) {
        $enterSawDown = $true
        $lines += "t=${t}s  ENTER went DOWN (start of hold)"
    }
    if ($enterSawDown -and -not $enterReleased) {
        if ($enter) {
            $zDuringHold += "t=${t}s ENTER=DOWN Z=$z"
        } else {
            $enterReleased = $true
            $lines += "t=${t}s  ENTER released"
            $lines += "  sampled states while ENTER was held:"
            $lines += ($zDuringHold | ForEach-Object { "    $_" })
        }
    }
    if ($enterReleased) {
        if ($null -eq $zAfterRelease) {
            $zAfterRelease = $z
            $lines += "t=${t}s  Z right after ENTER release = $z"
            break
        }
    }
    Start-Sleep -Milliseconds 100
}

if (-not $enterSawDown) { $lines += "ENTER was never seen as DOWN (nothing happened during the monitor window)" }
$lines += ""
$lines += "VERDICT:"
if ($enterSawDown -and $zDuringHold.Count -gt 0) {
    $allZdown = ($zDuringHold | Where-Object { $_ -like "*Z=True*" }).Count
    $lines += "  during ENTER hold: $allZdown of $($zDuringHold.Count) samples had Z=DOWN"
}
if ($null -ne $zAfterRelease) { $lines += "  after ENTER release: Z=$zAfterRelease (expect False)" }
Set-Content -Path $out -Value $lines -Encoding UTF8
