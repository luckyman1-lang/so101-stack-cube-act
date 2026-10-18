# ============================================================
#  01 找串口 / 扫摄像头
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1            列出当前串口
#     powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1 -Watch     拔一根 USB，自动告诉你是哪个口
#     powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1 -Cams -Snapshot   扫摄像头并存快照
#
#  找到后把端口填进 config\robot.ini：
#     从臂 -> [robot]  port
#     主臂 -> [teleop] port
# ============================================================
param(
    [switch]$Watch,
    [switch]$Cams,
    [switch]$Snapshot,
    [int]$MaxIndex = 6
)

. "$PSScriptRoot\_common.ps1"

Write-Head '串口 / 摄像头探测'

$argv = @(Join-Path $PSScriptRoot 'list_ports.py')
if ($Cams) { $argv += '--cams' }
if ($Snapshot) { $argv += '--snapshot' }
if ($Cams -and $MaxIndex -gt 0) { $argv += @('--max-index', "$MaxIndex") }
if ($Watch) { $argv += '--watch' }

Invoke-Lerobot -ArgList $argv

if (-not $Watch -and -not $Cams) {
    Write-Host ''
    Write-Host '提示：想确认哪个口对应哪个机械臂，加 -Watch：' -ForegroundColor Yellow
    Write-Host '      powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1 -Watch' -ForegroundColor Yellow
}
