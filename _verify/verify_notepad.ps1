# Temporary end-to-end verification for Task 2. Will be deleted after use.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-Editor {
    param($Root)
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Document)
    return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function Get-EditorText {
    param($Ed)
    try {
        $tp = $Ed.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
        return $tp.DocumentRange.GetText(-1)
    } catch {
        return "<TextPattern failed: " + $_.Exception.Message + ">"
    }
}

function Clear-Editor {
    param($Ed)
    $Ed.SetFocus()
    Start-Sleep -Milliseconds 400
    $tp = $Ed.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    $tp.DocumentRange.Select()
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait("{DEL}")
    Start-Sleep -Milliseconds 400
}

# clean slate
Get-Process -Name Notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1000

Start-Process "shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" | Out-Null
$np = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $np = Get-Process -Name Notepad -ErrorAction SilentlyContinue |
          Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($np) { break }
}
if (-not $np) { "FATAL: notepad window not found"; exit 1 }
$np.Refresh()
$h = $np.MainWindowHandle
Start-Sleep -Seconds 3
"notepad pid=$($np.Id) hwnd=$h title='$($np.MainWindowTitle)'"

$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$ed = Get-Editor $root
if (-not $ed) { "FATAL: editor element not found"; exit 1 }
"editor ok: class=" + $ed.Current.ClassName

Clear-Editor $ed
"A) after clear, text = [" + (Get-EditorText $ed) + "]"

# --- control run: exactly the same timing but NO key simulation at all ---
$ed.SetFocus()
Start-Sleep -Milliseconds 300
"foreground ok before control: " + ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.ClassName -eq "RichEditD2DPT")
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Start-Process powershell -WindowStyle Hidden -Wait -ArgumentList '-NoProfile','-Command','Start-Sleep -Milliseconds 3200'
$sw.Stop()
"B) CONTROL nokey elapsed=$([math]::Round($sw.Elapsed.TotalSeconds,2))s text=[" + (Get-EditorText $ed) + "]"

Clear-Editor $ed
"C) after clear, text = [" + (Get-EditorText $ed) + "]"

# --- real run: python main.py ---
$ed.SetFocus()
Start-Sleep -Milliseconds 300
$fgOk = ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.ClassName -eq "RichEditD2DPT")
"foreground ok before main.py: $fgOk"
$sw2 = [System.Diagnostics.Stopwatch]::StartNew()
$py = Start-Process python -ArgumentList 'main.py' -WindowStyle Hidden -Wait -PassThru -WorkingDirectory (Get-Location).Path
$sw2.Stop()
"--- main.py exit code: $($py.ExitCode)  elapsed=$([math]::Round($sw2.Elapsed.TotalSeconds,2))s ---"
Start-Sleep -Milliseconds 600

$text = Get-EditorText $ed
"D) python main.py text = [" + $text + "]"
"length=" + $text.Length
"equals_z=" + ($text -eq "z")
"contains_z=" + ($text.Contains("z"))

Start-Sleep -Milliseconds 500
Get-Process -Name Notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"notepad closed"
