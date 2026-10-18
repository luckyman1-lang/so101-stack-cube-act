# ============================================================
#  激活本项目的 LeRobot 环境（交互式使用）
#
#  推荐用法：双击 run_as_admin.cmd（会自动提权 + 调本脚本）
#  或者手动：本文件所在目录（D:\LeRobot）执行
#     . .\activate.ps1
#
#  激活后会：
#    * 把本项目的 python 加进 PATH（python / pip 都指向它）
#    * 切到项目根目录 D:\LeRobot —— 脚本里大量用相对路径
#      （scripts\xxx.ps1），不切的话会报「文件不存在」
#    * 设好 HF 缓存目录（含机械臂校准文件）、临时目录、UTF-8 编码
#    * 让相机走 DSHOW 后端（本机 Orbbec Gemini 2 的 UVC 接口只有
#      DSHOW 能出图，MSMF 扫不到任何索引）
#
#  本脚本只影响当前这个 PowerShell 窗口，关掉就没了。
# ============================================================

$root = $PSScriptRoot
$pyDir = Join-Path $root '_tools\python310'
$pyExe = Join-Path $pyDir 'python.exe'

if (-not (Test-Path -LiteralPath $pyExe)) {
    Write-Host "找不到 Python：$pyExe" -ForegroundColor Red
    Write-Host '环境没装好，请先看 README.md 的「一、环境」部分。' -ForegroundColor Red
    return
}

# 切到项目根目录：所有 scripts\*.ps1 的示例命令都假定当前目录是这里
Set-Location -LiteralPath $root

# PATH：让 python / pip 指向本项目的解释器
if ($env:Path -notlike "*$pyDir*") {
    $env:Path = "$pyDir;$(Join-Path $pyDir 'Scripts');$env:Path"
}

# 临时目录 + UTF-8，避免中文输出乱码
$tmp = Join-Path $root '_tools\tmp'
if (-not (Test-Path -LiteralPath $tmp)) { New-Item -ItemType Directory -Force -Path $tmp | Out-Null }
$env:TEMP = $tmp
$env:TMP = $tmp
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

# HuggingFace / LeRobot 缓存与校准文件都放项目内（见 scripts\_common.ps1 的说明）。
# 注意：这样校准文件在 D:\LeRobot\_tools\hf-cache\lerobot\calibration，
# 以后跑 lerobot 命令都用本脚本激活，路径才一致。
$env:HF_HOME = Join-Path $root '_tools\hf-cache'
$env:HF_LEROBOT_CALIBRATION = Join-Path $env:HF_HOME 'lerobot\calibration'
$env:HF_HUB_DISABLE_TELEMETRY = '1'

# 本机 Orbbec Gemini 2 的 UVC 接口只有 DSHOW 后端能出图（MSMF 扫不到）。
# 以后换回普通 USB 摄像头可以删掉这行。
$env:LEROBOT_CV2_BACKEND = 'DSHOW'

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
} catch { }

$ver = & $pyExe -c "import sys; print(sys.version.split()[0])"

Write-Host ''
Write-Host '  LeRobot 环境已激活' -ForegroundColor Green
Write-Host "    python   : $pyExe  ($ver)"
Write-Host "    工作目录 : $root"
Write-Host "    配置     : $root\config\robot.ini"
Write-Host ''
Write-Host '  常用命令（当前目录已切到项目根，可直接跑）：' -ForegroundColor Cyan
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1        环境自检'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1       找串口'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1        校准机械臂'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1      遥操作测试'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1   采集数据集'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1        训练模型'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1       推理'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\check_calibration.ps1   校准体检'
Write-Host '    python _setup\preview_cameras.py                                          相机实时预览'
Write-Host ''
Write-Host '  采集数据：必须用【管理员权限】的窗口（相机要提权），并加 -NoRerun' -ForegroundColor Yellow
Write-Host '    （不加 -NoRerun 会启动 rerun 可视化窗口，在本机 Vulkan 下会崩溃）' -ForegroundColor Yellow
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 5 -NoRerun' -ForegroundColor Yellow
Write-Host ''
