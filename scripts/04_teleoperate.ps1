# ============================================================
#  03 遥操作：手动拖主臂，从臂跟随（采集数据前先在这里练手）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1 -DryRun
#
#  说明：
#   * 第一次运行会要求重新校准从臂，按提示操作即可
#   * 结束用 Ctrl+C
#   * 这一关过了再采集数据（scripts\05_record_dataset.ps1）
# ============================================================
param(
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

$robotPort = Get-Cfg -Config $cfg -Section 'robot'  -Key 'port'
$robotId   = Get-Cfg -Config $cfg -Section 'robot'  -Key 'id'   -Default 'my_follower'
$telePort  = Get-Cfg -Config $cfg -Section 'teleop' -Key 'port'
$teleId    = Get-Cfg -Config $cfg -Section 'teleop' -Key 'id'   -Default 'my_leader'

Assert-Port -Port $robotPort -Who '从臂([robot] port)'
Assert-Port -Port $telePort  -Who '主臂([teleop] port)'

Write-Head '遥操作测试（拖动主臂，从臂应跟随）'
Write-Host '  按 Ctrl+C 结束。' -ForegroundColor Yellow

Invoke-Lerobot -DryRun:$DryRun -ArgList @(
    '-m', 'lerobot.teleoperate',
    '--robot.type=so101_follower',
    "--robot.port=$robotPort",
    "--robot.id=$robotId",
    '--teleop.type=so101_leader',
    "--teleop.port=$telePort",
    "--teleop.id=$teleId"
)
