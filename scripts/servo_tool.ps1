# ============================================================
#  Seeed 舵机调试工具的启动器（GUI + 命令行小工具）
#
#  前提：先跑过 scripts\install_servo_debug_tool.ps1
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1                 # 打开 GUI
#     powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool scan --list
#     powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool disable
#
#  可选 -Tool：
#     gui               图形界面（检测舵机 / 改 ID / 中位 / 单舵机控制）
#     scan              扫描总线上有哪些舵机 ID
#     change-id         改写单个舵机的 ID（改之前总线上只能接这一个舵机！）
#     middle            把当前位置写成中位值
#     center-test       中位测试（看机械臂中位是否正常）
#     disable           失能电机（机械臂会"软"下来，用手扶住）
#     diag              读寄存器做诊断
#     lerobot-calibrate 用这个工具做 LeRobot 的整臂校准
#     calib-middle      走一遍"中位校准"流程
# ============================================================
param(
    [ValidateSet('gui', 'scan', 'change-id', 'middle', 'center-test',
                 'disable', 'diag', 'lerobot-calibrate', 'calib-middle')]
    [string]$Tool = 'gui',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$root    = Split-Path -Parent $PSScriptRoot
$py      = Join-Path $root '_tools\python310\python.exe'
$repoDir = Join-Path $root '_tools\Seeed_RoboController'
$pkgDir  = Join-Path $root '_tools\py-servo-debug'

if (-not (Test-Path $repoDir)) {
    throw "还没安装舵机调试工具。先运行：`n  powershell -ExecutionPolicy Bypass -File scripts\install_servo_debug_tool.ps1"
}
if (-not (Test-Path $pkgDir)) {
    throw "依赖目录不存在：$pkgDir`n请重新运行 install_servo_debug_tool.ps1"
}

$modules = @{
    'gui'               = 'src.gui.factory_calibration_tool'
    'scan'              = 'src.tools.scan_id'
    'change-id'         = 'src.tools.change_single_servo_id'
    'middle'            = 'src.tools.servo_middle_calibration'
    'center-test'       = 'src.tools.servo_center_test'
    'disable'           = 'src.tools.servo_disable'
    'diag'              = 'src.tools.servo_register_diag'
    'lerobot-calibrate' = 'src.tools.lerobot_calibrate'
    'calib-middle'      = 'src.tools.run_calibration_middle'
}

$module = $modules[$Tool]
$env:PYTHONPATH = $pkgDir
# 让这个工具也用 UTF-8 输出，否则它按本地编码（GBK）打印的中文
# 会在我们已经切成 UTF-8 的控制台里变成乱码
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host ''
Write-Host "运行 $module $($ExtraArgs -join ' ')" -ForegroundColor Cyan
Write-Host ''

Push-Location $repoDir
try {
    & $py -m $module @ExtraArgs
}
finally {
    Pop-Location
}
