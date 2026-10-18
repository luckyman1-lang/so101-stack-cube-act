# ============================================================
#  02 校准机械臂（主臂、从臂各校准一次，结果会存到本地）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1              主臂+从臂都校准
#     powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1 -Arm follower
#     powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1 -Arm leader
#     powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1 -DryRun      只看命令不执行
#
#  操作流程（脚本会提示）：
#     1) 把机械臂所有关节摆到"活动范围的中间位置"，按回车
#     2) 依次把每个关节从最小推到最大（走完全程）
#     3) 再按回车结束，终端会打印 MIN/POS/MAX 一张表
#
#  注意：
#   * 从臂要接 12V 电源，主臂接 5V；USB 只通信不供电
#   * 校准数据保存在 %USERPROFILE%\.cache\huggingface\lerobot\calibration
#     （每台机械臂的 id 对应一个文件，换电脑要一起拷过去）
# ============================================================
param(
    [ValidateSet('follower', 'leader', 'both')]
    [string]$Arm = 'both',
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

function Invoke-Calibrate {
    param([string]$Which)

    if ($Which -eq 'follower') {
        Write-Head '校准从臂 SO101Follower（白色）'
        $port = Get-Cfg -Config $cfg -Section 'robot' -Key 'port'
        Assert-Port -Port $port -Who '从臂([robot] port)'
        $id = Get-Cfg -Config $cfg -Section 'robot' -Key 'id' -Default 'my_follower'
        Invoke-Lerobot -DryRun:$DryRun -ArgList @(
            '-m', 'lerobot.calibrate',
            '--robot.type=so101_follower',
            "--robot.port=$port",
            "--robot.id=$id"
        )
    }
    else {
        Write-Head '校准主臂 SO101Leader（黑色）'
        $port = Get-Cfg -Config $cfg -Section 'teleop' -Key 'port'
        Assert-Port -Port $port -Who '主臂([teleop] port)'
        $id = Get-Cfg -Config $cfg -Section 'teleop' -Key 'id' -Default 'my_leader'
        Invoke-Lerobot -DryRun:$DryRun -ArgList @(
            '-m', 'lerobot.calibrate',
            '--teleop.type=so101_leader',
            "--teleop.port=$port",
            "--teleop.id=$id"
        )
    }
}

Write-Host '校准前请确认：机械臂电源已接通、USB 已插好、桌面空间足够。' -ForegroundColor Yellow
Write-Host '提示：关节处于"中间位置"时按回车，然后每个关节都要走完全程。' -ForegroundColor Yellow

if ($Arm -eq 'follower' -or $Arm -eq 'both') { Invoke-Calibrate 'follower' }
if ($Arm -eq 'leader'   -or $Arm -eq 'both') { Invoke-Calibrate 'leader' }

Write-Host ''
Write-Host '校准完成。下一步：scripts\04_teleoperate.ps1 试试主从跟随。' -ForegroundColor Green
