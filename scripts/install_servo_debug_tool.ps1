# ============================================================
#  可选工具：Seeed 舵机调试 GUI（Seeed_RoboController）
#
#  用途（来自 Seeed 官方 Wiki）：当机械臂出现下面这些情况时用它排查
#    * 校准/遥操作时某个舵机没反应、或报 "Magnitude exceeds 2047"
#    * 怀疑舵机 ID 重复（校准时把"校准整臂"的指令误敲成了"校准舵机"）
#    * 需要把某个位置写成"中位值"、或读寄存器/改波特率/恢复出厂
#    * 想单独手动控制某一个舵机看它是否正常
#
#  为什么把依赖装到独立目录而不是虚拟环境：
#    它需要 PySide6（GUI），装进主环境有影响主环境依赖的风险，所以隔离；
#    但本机**建 venv 会失败** —— venv 里的 python 不加载基础环境的 sitecustomize
#    （include-system-site-packages=false），于是 ensurepip 在未打补丁的状态下运行，
#    又踩到"临时目录权限被拒"那个坑（见 README 坑 2/15）。
#    改用 `pip install --target <目录>` + PYTHONPATH 同样能隔离，而且用的是
#    已经打了补丁的解释器。
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\install_servo_debug_tool.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\install_servo_debug_tool.ps1 -Run    # 装完直接启动
# ============================================================
param(
    [switch]$Run,
    [switch]$Force
)

$ErrorActionPreference = 'Continue'
# 注意：刻意不用 'Stop'。PowerShell 5.1 在 Stop 模式下会把原生命令（git / pip）
# 写到 stderr 的进度信息当成终结性错误直接中断，所以用 Continue 并自己检查退出码。
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$root     = Split-Path -Parent $PSScriptRoot
$py       = Join-Path $root '_tools\python310\python.exe'
$repoDir  = Join-Path $root '_tools\Seeed_RoboController'
$pkgDir   = Join-Path $root '_tools\py-servo-debug'
$oldVenv  = Join-Path $root '_tools\envs\servo-debug'

# 沙箱/本机下 git 默认的 schannel 后端握手会失败，强制用 openssl 后端
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'http.sslBackend'
$env:GIT_CONFIG_VALUE_0 = 'openssl'
$env:TEMP = Join-Path $root '_tools\tmp'
$env:TMP  = $env:TEMP
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

Write-Host ''
Write-Host '=== 1/4 获取 Seeed_RoboController ===' -ForegroundColor Cyan
if ((Test-Path $repoDir) -and -not $Force) {
    Write-Host "已存在，跳过下载：$repoDir（想重新拉取加 -Force）"
}
else {
    Remove-Item -Recurse -Force $repoDir -ErrorAction SilentlyContinue
    # 该仓库的默认分支叫 factory（不是 main）
    git clone --depth 1 https://github.com/Seeed-Projects/Seeed_RoboController.git $repoDir
    $cloneOk = ($LASTEXITCODE -eq 0) -and (Test-Path $repoDir)

    if ((-not $cloneOk) -and (Test-Path $repoDir)) {
        # 本机 git 走 sh 过滤器时可能崩在 checkout（README 坑 7），用 plumbing 补落盘
        Write-Host '克隆返回非 0，尝试用 git plumbing 补齐工作区...' -ForegroundColor Yellow
        git -C $repoDir read-tree HEAD
        git -C $repoDir checkout-index -a -f
        $cloneOk = Test-Path $repoDir
    }
    if (-not $cloneOk) {
        # git 不通时（schannel 不可用 / 连接被重置）改用 Python 下 tar 包
        Write-Host 'git 克隆失败，改用 Python 下载仓库压缩包...' -ForegroundColor Yellow
        Remove-Item -Recurse -Force $repoDir -ErrorAction SilentlyContinue
        & $py (Join-Path $root '_setup\fetch_repo.py') 'Seeed-Projects/Seeed_RoboController' 'factory' $repoDir
        if ($LASTEXITCODE -ne 0) { throw '获取仓库失败，请检查网络后重试' }
    }
}
if (-not (Test-Path $repoDir)) { throw "获取仓库失败：$repoDir 不存在" }
Get-ChildItem $repoDir | Select-Object -First 12 -ExpandProperty Name | ForEach-Object { "    $_" }

Write-Host ''
Write-Host '=== 2/4 把 GUI 依赖装到独立目录 ===' -ForegroundColor Cyan
Write-Host "    目标目录：$pkgDir"
if (Test-Path $pkgDir) { Remove-Item -Recurse -Force $pkgDir -ErrorAction SilentlyContinue }
& $py -m pip install --target $pkgDir --upgrade --index-url https://pypi.org/simple PySide6 pyserial
if ($LASTEXITCODE -ne 0) {
    throw "依赖安装失败。可以手工重试：`n  & `"$py`" -m pip install --target `"$pkgDir`" PySide6 pyserial"
}

# 顺手清掉早年失败留下的空 venv（删不掉就跳过）
if (Test-Path $oldVenv) {
    Remove-Item -Recurse -Force $oldVenv -ErrorAction SilentlyContinue
    if (Test-Path $oldVenv) { Write-Host "    （残留的旧 venv 删不掉，可在资源管理器里手动删除：$oldVenv）" -ForegroundColor Yellow }
}

Write-Host ''
Write-Host '=== 3/4 工具自带的环境自检 ===' -ForegroundColor Cyan
$env:PYTHONPATH = $pkgDir
Push-Location $repoDir
try {
    if (Test-Path (Join-Path $repoDir 'setup.py')) { & $py setup.py }
    else { Write-Host '（仓库里没有 setup.py，跳过自检）' -ForegroundColor Yellow }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host '=== 4/4 完成 ===' -ForegroundColor Green
Write-Host '启动 GUI（选择串口后即可检测 1-6 号舵机）：'
Write-Host "  cd `"$repoDir`""
Write-Host "  `$env:PYTHONPATH = `"$pkgDir`""
Write-Host "  & `"$py`" -m src.gui.factory_calibration_tool"

if ($Run) {
    Write-Host ''
    Write-Host '正在启动 GUI...' -ForegroundColor Cyan
    Push-Location $repoDir
    try { & $py -m src.gui.factory_calibration_tool }
    finally { Pop-Location }
}
