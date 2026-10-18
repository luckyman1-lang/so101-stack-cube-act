# ============================================================
#  02 舵机 ID / 波特率设置（**只有散件才需要**；买的是组装好的整臂请直接跳到 03）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\02_setup_motors.ps1              # 从臂
#     powershell -ExecutionPolicy Bypass -File scripts\02_setup_motors.ps1 -Arm leader  # 主臂
#     powershell -ExecutionPolicy Bypass -File scripts\02_setup_motors.ps1 -DryRun
#
#  为什么需要这一步：出厂的 STS3215 舵机默认都是同一个 ID（通常是 1），
#  一条总线上如果有两个同 ID 的舵机，改 ID 时会把它们一起改掉，
#  所以必须**一次只接一个舵机**，由脚本逐个写入 ID。
#
#  操作要点（来自 Seeed 官方流程）：
#   1. 接线：电脑 → USB → 舵机驱动板 → 三针线 → **只接一个**舵机
#   2. 脚本会按 6→5→4→3→2→1（夹爪 → 底座）的顺序逐个提示，每次按回车前
#      务必确认"当前只有这一个舵机接着"
#   3. 先接好电源再插 USB；USB 不给舵机供电
#      Leader 用 5V；Follower 标准版 5V、Pro 版 12V —— 接错电压会烧舵机
#   4. SO-101 的 Leader 前三个关节减速比与 SO-100 不同，接线前先对照型号表
# ============================================================
param(
    [ValidateSet('follower', 'leader')]
    [string]$Arm = 'follower',
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

Write-Host '这一步会逐个给舵机写入 ID 和波特率。' -ForegroundColor Yellow
Write-Host '开始前请确认：' -ForegroundColor Yellow
Write-Host '  * 电源已按正确电压接好（Leader 5V / Follower 标准版 5V、Pro 版 12V）'
Write-Host '  * 当前**只把 1 个舵机**接到驱动板上'
Write-Host '  * 机械臂此时还没有组装（散件状态）'

if ($Arm -eq 'follower') {
    Write-Head '设置从臂舵机 SO101Follower（白色）'
    $port = Get-Cfg -Config $cfg -Section 'robot' -Key 'port'
    Assert-Port -Port $port -Who '从臂([robot] port)'
    Invoke-Lerobot -DryRun:$DryRun -ArgList @(
        '-m', 'lerobot.setup_motors',
        '--robot.type=so101_follower',
        "--robot.port=$port"
    )
}
else {
    Write-Head '设置主臂舵机 SO101Leader（黑色）'
    $port = Get-Cfg -Config $cfg -Section 'teleop' -Key 'port'
    Assert-Port -Port $port -Who '主臂([teleop] port)'
    Invoke-Lerobot -DryRun:$DryRun -ArgList @(
        '-m', 'lerobot.setup_motors',
        '--teleop.type=so101_leader',
        "--teleop.port=$port"
    )
}

Write-Host ''
Write-Host '提示：这一步和"整臂校准"是两件事。' -ForegroundColor Cyan
Write-Host '  * 这里：给每个舵机写 ID / 波特率（散件组装前做）'
Write-Host '  * 03_calibrate：整臂装好后校准每个关节的活动范围'
