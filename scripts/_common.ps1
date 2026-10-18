# ============================================================
#  公共工具：定位解释器、读取 config\robot.ini、拼装 lerobot 参数
#
#  其它脚本用点号加载：
#      . "$PSScriptRoot\_common.ps1"
# ============================================================

$ErrorActionPreference = 'Stop'

$script:CommonDir = $PSScriptRoot
if (-not $script:CommonDir) { $script:CommonDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }
$script:ProjectRoot = Split-Path -Parent $script:CommonDir
$script:PythonExe   = Join-Path $script:ProjectRoot '_tools\python310\python.exe'
$script:ConfigPath  = Join-Path $script:ProjectRoot 'config\robot.ini'
$script:TmpDir      = Join-Path $script:ProjectRoot '_tools\tmp'

# 临时目录放到工作区内；同时强制 UTF-8，避免中文/emoji 日志在 GBK 控制台报错
if (-not (Test-Path $script:TmpDir)) { New-Item -ItemType Directory -Force -Path $script:TmpDir | Out-Null }
$env:TEMP = $script:TmpDir
$env:TMP  = $script:TmpDir
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

# HuggingFace / LeRobot 的缓存、数据集下载缓存、机械臂校准文件，全部放在项目内：
#  * 沙箱只允许写工作区，默认的 C:\Users\<你>\.cache\huggingface 会写失败
#  * 放项目里便于整体备份/迁移，尤其是 calibration（换机器要带走）
$env:HF_HOME = Join-Path $script:ProjectRoot '_tools\hf-cache'
$env:HF_LEROBOT_CALIBRATION = Join-Path $env:HF_HOME 'lerobot\calibration'
$env:HF_HUB_DISABLE_TELEMETRY = '1'

# torchvision 的预训练权重（ResNet18 等）：默认下到 C:\Users\<你>\.cache\torch，
# 沙箱写不进去，会报 PermissionError [WinError 5]。指到项目内。
$env:TORCH_HOME = Join-Path $script:ProjectRoot '_tools\torch-cache'

# 相机的自动白平衡（AWB）会在两次开相机之间漂移，导致同一场景色调变掉 ——
# 实测录数据时红块 H≈21（橙红），推理时漂成 H≈100（偏蓝），策略认不出目标。
# 这里固定关闭 AWB 并锁死色温。5800K 是 scan_wb.py 实测出来的最接近录制时的值
# （红块 H=24 / S=98，录制时是 H=21 / S=125）。
# 换相机或换了灯光环境后，重跑 _setup\scan_wb.py 重新找一个合适的色温。
$env:LEROBOT_CAM_AWB = 'off'
$env:LEROBOT_CAM_AWB_TEMP = '5800'

# 本机的 Orbbec Gemini 2（UVC 接口）只有在 DSHOW 后端下才能出图：
# MSMF 后端扫不到任何索引，而 DSHOW 能正常拿到彩色画面。
# lerobot 默认在 Windows 用 MSMF，所以这里覆盖成 DSHOW。
# 以后若换回普通 USB 摄像头，可以删掉这行或改成 'MSMF'。
$env:LEROBOT_CV2_BACKEND = 'DSHOW'

# 把环境的 Scripts 目录加进 PATH：rerun.exe（录制/可视化要用）、swanlab、
# huggingface-cli、pyserial-ports 等都在这里
$script:ScriptsDir = Join-Path (Split-Path -Parent $script:PythonExe) 'Scripts'
if ((Test-Path $script:ScriptsDir) -and ($env:Path -notlike "*$script:ScriptsDir*")) {
    $env:Path = "$script:ScriptsDir;$env:Path"
}

# 让控制台按 UTF-8 解码 Python 输出，中文才不会变成乱码
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
} catch { }

# ------------------------------------------------------------
# 配置读取
# ------------------------------------------------------------
function Get-IniConfig {
    param([string]$Path = $script:ConfigPath)

    if (-not (Test-Path -LiteralPath $Path)) { throw "找不到配置文件：$Path" }

    $cfg = @{}
    $section = 'global'
    $cfg[$section] = @{}

    foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $raw.Trim()
        if ($line -eq '' -or $line.StartsWith('#') -or $line.StartsWith(';')) { continue }

        if ($line -match '^\[(.+)\]$') {
            $section = $Matches[1].Trim()
            if (-not $cfg.ContainsKey($section)) { $cfg[$section] = @{} }
            continue
        }

        $i = $line.IndexOf('=')
        if ($i -lt 1) { continue }
        $key = $line.Substring(0, $i).Trim()
        $val = $line.Substring($i + 1).Trim()
        $cfg[$section][$key] = $val
    }
    return $cfg
}

function Get-Cfg {
    param($Config, [string]$Section, [string]$Key, [string]$Default = '')
    if ($Config.ContainsKey($Section) -and $Config[$Section].ContainsKey($Key)) {
        $v = $Config[$Section][$Key]
        if ($v -ne '') { return $v }
    }
    return $Default
}

function Get-CfgBool {
    param($Config, [string]$Section, [string]$Key, [bool]$Default = $false)
    $v = Get-Cfg -Config $Config -Section $Section -Key $Key
    if ($v -eq '') { return $Default }
    return @('true', '1', 'yes', 'on') -contains $v.ToLower()
}

function Get-CfgInt {
    param($Config, [string]$Section, [string]$Key, [int]$Default = 0)
    $v = Get-Cfg -Config $Config -Section $Section -Key $Key
    if ($v -eq '') { return $Default }
    return [int]$v
}

function Format-Bool {
    param([bool]$Value)
    if ($Value) { return 'true' }
    return 'false'
}

# ------------------------------------------------------------
# 检查
# ------------------------------------------------------------
function Assert-Python {
    if (-not (Test-Path -LiteralPath $script:PythonExe)) {
        throw "找不到 Python 解释器：$script:PythonExe`n请先按 README 的『一、安装环境』准备环境。"
    }
}

function Assert-Port {
    param([string]$Port, [string]$Who)
    if (-not $Port -or $Port -eq 'CHANGE_ME') {
        throw "$Who 的串口还没配置。请先运行：`n  powershell -ExecutionPolicy Bypass -File `"$script:CommonDir\01_find_ports.ps1`"`n然后把 config\robot.ini 里的 $Who 端口填上（形如 COM3）。"
    }
    if ($Port -notmatch '^COM\d+$') {
        throw "$Who 的串口 '$Port' 看起来不像 Windows 串口。Windows 上应形如 COM3、COM12。"
    }
}

function Assert-Camera {
    param($Config, [string]$Who)
    if (-not (Get-CfgBool -Config $Config -Section 'cameras' -Key "${Who}_enabled" -Default $false)) {
        throw "配置文件里没有启用任何摄像头（cameras\${Who}_enabled = false）。采集数据必须有至少一个摄像头。"
    }
}

# ------------------------------------------------------------
# 参数拼装
# ------------------------------------------------------------
# 摄像头 -> lerobot 的 --robot.cameras="{front: {type: opencv, index_or_path: 0, ...}}"
function Get-CameraArg {
    param($Config)
    $parts = @()
    foreach ($name in @('front', 'wrist')) {
        if (Get-CfgBool -Config $Config -Section 'cameras' -Key "${name}_enabled" -Default $false) {
            $idx = Get-Cfg    -Config $Config -Section 'cameras' -Key "${name}_index"  -Default '0'
            $w   = Get-Cfg    -Config $Config -Section 'cameras' -Key "${name}_width"  -Default '640'
            $h   = Get-Cfg    -Config $Config -Section 'cameras' -Key "${name}_height" -Default '480'
            $fps = Get-Cfg    -Config $Config -Section 'cameras' -Key "${name}_fps"    -Default '30'
            $parts += "${name}: {type: opencv, index_or_path: $idx, width: $w, height: $h, fps: $fps}"
        }
    }
    if ($parts.Count -eq 0) { return $null }
    return '{' + ($parts -join ', ') + '}'
}

# 数据集实际目录：默认 root_dir\数据集名（LeRobot 的 --dataset.root 就是数据集本目录）
function Get-DatasetRoot {
    param($Config, [string]$RepoId, [string]$Section = 'dataset')
    $explicit = Get-Cfg -Config $Config -Section $Section -Key 'root'
    if ($explicit) { return $explicit }
    $rootDir = Get-Cfg -Config $Config -Section 'dataset' -Key 'root_dir'
    if (-not $rootDir) { $rootDir = Join-Path $script:ProjectRoot 'datasets' }
    $name = $RepoId
    if ($name.Contains('/')) { $name = $name.Split('/')[-1] }
    return (Join-Path $rootDir $name)
}

# 从臂参数
function Get-RobotArgs {
    param($Config)
    $port = Get-Cfg -Config $Config -Section 'robot' -Key 'port'
    $id   = Get-Cfg -Config $Config -Section 'robot' -Key 'id' -Default 'my_follower'
    $cam  = Get-CameraArg -Config $Config
    $a = @(
        '--robot.type=so101_follower',
        "--robot.port=$port",
        "--robot.id=$id"
    )
    if ($cam) { $a += "--robot.cameras=$cam" }
    return $a
}

# 主臂参数
function Get-TeleopArgs {
    param($Config)
    $port = Get-Cfg -Config $Config -Section 'teleop' -Key 'port'
    $id   = Get-Cfg -Config $Config -Section 'teleop' -Key 'id' -Default 'my_leader'
    return @(
        '--teleop.type=so101_leader',
        "--teleop.port=$port",
        "--teleop.id=$id"
    )
}

# ------------------------------------------------------------
# 执行
# ------------------------------------------------------------
function Invoke-Lerobot {
    param(
        [Parameter(Mandatory = $true)][string[]]$ArgList,
        [switch]$DryRun
    )
    Assert-Python
    $shown = $ArgList | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
    Write-Host ''
    Write-Host ("> python " + ($shown -join ' ')) -ForegroundColor DarkGray
    Write-Host ''
    if ($DryRun) {
        Write-Host '(DryRun：只打印命令，未真正执行)' -ForegroundColor Yellow
        return
    }
    & $script:PythonExe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "命令执行失败，退出码 $LASTEXITCODE" }
}

function Write-Head {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 60) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ('=' * 60) -ForegroundColor Cyan
}
