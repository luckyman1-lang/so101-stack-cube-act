# ============================================================
#  05 训练 ACT 策略（本机 GPU）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -Steps 20000
#     powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -Resume           接着上次训练
#     powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -SwanlabMode cloud 用云端 SwanLab
#     powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -DryRun
#
#  显存不够时（8G 卡常见）：
#     scripts\06_train_act.ps1 -BatchSize 4      或  -BatchSize 2
#     还不行就  -NumWorkers 0
#
#  产物：<train.output_dir>\checkpoints\<步数>\pretrained_model
#        以及 checkpoints\last（最新一次）
# ============================================================
param(
    [int]$Steps = 0,
    [int]$BatchSize = 0,
    [int]$NumWorkers = -1,
    [int]$SaveFreq = 0,
    [int]$LogFreq = 0,
    [string]$SwanlabMode = '',
    [switch]$Resume,
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

# ---------- 数据集 ----------
$repo = Get-Cfg -Config $cfg -Section 'dataset' -Key 'repo_id'
$root = Get-DatasetRoot -Config $cfg -RepoId $repo

if (-not (Test-Path -LiteralPath $root)) {
    throw "找不到数据集目录：$root`n先把数据采集好（scripts\05_record_dataset.ps1），或修正 config\robot.ini 里的 repo_id / root_dir。"
}

# ---------- 训练参数 ----------
$policy     = Get-Cfg    -Config $cfg -Section 'train' -Key 'policy'      -Default 'act'
$outputDir  = Get-Cfg    -Config $cfg -Section 'train' -Key 'output_dir'  -Default (Join-Path $script:ProjectRoot 'outputs\train\pick_cube')
$jobName    = Get-Cfg    -Config $cfg -Section 'train' -Key 'job_name'    -Default 'pick_cube'
$policyRepo = Get-Cfg    -Config $cfg -Section 'train' -Key 'policy_repo_id' -Default 'local/policy'
$device     = Get-Cfg    -Config $cfg -Section 'train' -Key 'device'      -Default 'cuda'
$tracker    = Get-Cfg    -Config $cfg -Section 'train' -Key 'tracker'     -Default 'swanlab'
$swProject  = Get-Cfg    -Config $cfg -Section 'train' -Key 'swanlab_project' -Default 'lerobot'
$swMode     = $SwanlabMode
if (-not $swMode) { $swMode = Get-Cfg -Config $cfg -Section 'train' -Key 'swanlab_mode' -Default 'offline' }

$stepsFinal = $Steps
if ($stepsFinal -le 0) { $stepsFinal = Get-CfgInt -Config $cfg -Section 'train' -Key 'steps' -Default 40000 }

$batchFinal = $BatchSize
if ($batchFinal -le 0) { $batchFinal = Get-CfgInt -Config $cfg -Section 'train' -Key 'batch_size' -Default 8 }

$workersFinal = $NumWorkers
if ($workersFinal -lt 0) { $workersFinal = Get-CfgInt -Config $cfg -Section 'train' -Key 'num_workers' -Default 4 }

$saveFreq = $SaveFreq
if ($saveFreq -le 0) { $saveFreq = Get-CfgInt -Config $cfg -Section 'train' -Key 'save_freq' -Default 10000 }
$logFreq = $LogFreq
if ($logFreq -le 0) { $logFreq = Get-CfgInt -Config $cfg -Section 'train' -Key 'log_freq' -Default 100 }

Write-Head "训练 $policy 策略"
Write-Host "  数据集    : $repo"
Write-Host "  数据目录  : $root"
Write-Host "  输出目录  : $outputDir"
Write-Host "  步数      : $stepsFinal    batch_size: $batchFinal    workers: $workersFinal"
Write-Host "  设备      : $device"
Write-Host "  追踪      : $tracker (swanlab mode=$swMode)"
Write-Host ''
Write-Host '  训练时间参考：4060(8G) + 50 组数据约 6 小时；步数越多越久，可先跑 2 万步看 loss。' -ForegroundColor Yellow

$argv = @(
    '-m', 'lerobot.scripts.train',
    "--dataset.repo_id=$repo",
    "--dataset.root=$root",
    "--policy.type=$policy",
    "--policy.device=$device",
    "--policy.repo_id=$policyRepo",
    "--output_dir=$outputDir",
    "--job_name=$jobName",
    "--steps=$stepsFinal",
    "--batch_size=$batchFinal",
    "--num_workers=$workersFinal",
    "--save_freq=$saveFreq",
    "--log_freq=$logFreq",
    '--wandb.enable=false',
    # 本机没有 HF 账号/网络：训练结束后不去建 repo，否则会卡在连接 huggingface.co 超时
    '--policy.push_to_hub=false',
    "--tracker=$tracker"
)
if ($tracker -eq 'swanlab' -or $tracker -eq 'both') {
    $argv += @("--swanlab.project=$swProject", "--swanlab.mode=$swMode")
}
if ($Resume) { $argv += '--resume=true' }

Invoke-Lerobot -ArgList $argv -DryRun:$DryRun

if (-not $DryRun) {
    Write-Host ''
    Write-Host "训练完成。模型在：$outputDir\checkpoints\last\pretrained_model" -ForegroundColor Green
    Write-Host '下一步：scripts\07_run_policy.ps1 让机械臂自己抓。' -ForegroundColor Green
}
