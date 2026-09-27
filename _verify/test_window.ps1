# 专用测试窗口：面积大、位置固定、自己记录收到的鼠标/键盘事件，不做任何危险操作。
# 用法: powershell -File _verify\test_window.ps1 <事件日志路径>
param([Parameter(Mandatory = $true)][string]$LogPath)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "DSH Task7 input sink (safe)"
$form.StartPosition = "Manual"
$form.Location = New-Object System.Drawing.Point(60, 60)
$form.Size = New-Object System.Drawing.Size(900, 640)
$form.TopMost = $true
$form.KeyPreview = $true

$label = New-Object System.Windows.Forms.Label
$label.Dock = "Fill"
$label.Font = New-Object System.Drawing.Font("Consolas", 20)
$label.TextAlign = "MiddleCenter"
$label.Text = "waiting for input..."
$form.Controls.Add($label)

$script:logPath = $LogPath
$script:log = New-Object System.Collections.Generic.List[string]
function Add-Log([string]$line) {
    $script:log.Add($line)
    Set-Content -Path $script:logPath -Value $script:log -Encoding UTF8
}

$form.Add_MouseDown({
    param($sender, $e)
    $name = $e.Button.ToString()
    Add-Log "MouseDown:$name"
    $label.Text = "Mouse DOWN: $name"
})
$form.Add_MouseUp({
    param($sender, $e)
    $name = $e.Button.ToString()
    Add-Log "MouseUp:$name"
    $label.Text = "Mouse UP: $name"
})
$form.Add_KeyDown({
    param($sender, $e)
    $name = $e.KeyCode.ToString()
    Add-Log "KeyDown:$name"
    $label.Text = "Key DOWN: $name"
})
$form.Add_KeyUp({
    param($sender, $e)
    $name = $e.KeyCode.ToString()
    Add-Log "KeyUp:$name"
    $label.Text = "Key UP: $name"
})

Add-Log "window-ready"
[void]$form.ShowDialog()
