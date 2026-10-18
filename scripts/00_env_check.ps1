# ============================================================
#  00 环境自检：确认这套环境能跑（不需要机械臂）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1 -Quick      跳过采集链路验证
#     powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1 -Camera 0  额外测摄像头 0
# ============================================================
param(
    [switch]$Quick,
    [int]$Camera = -1
)

. "$PSScriptRoot\_common.ps1"

Write-Head 'LeRobot 环境自检'

$argv = @(Join-Path $PSScriptRoot '00_env_check.py')
if (-not $Quick) { $argv += '--dataset' }
if ($Camera -ge 0) { $argv += @('--camera', "$Camera") }

Invoke-Lerobot -ArgList $argv
