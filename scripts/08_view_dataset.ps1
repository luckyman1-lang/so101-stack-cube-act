# ============================================================
#  08 本地查看数据集（采集完先确认数据质量，再拿去训练）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1 -Episode 3
#     powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1 -Save          # 存 .rrd 文件，不弹窗
#     powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1 -RepoId local/eval_pick_cube_v1
#
#  说明：
#   * 默认弹 rerun 窗口，逐帧显示相机的画面 + 每个关节的 action / state 曲线
#   * 加 -Save 时把这一轮导出成 .rrd，之后可以用 rerun 命令离线打开
#   * 只读操作，不会修改数据集
# ============================================================
param(
    [int]$Episode = 0,
    [string]$RepoId = '',
    [string]$Root = '',
    [switch]$Save,
    [int]$NumWorkers = 0,
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

$repo = $RepoId
if (-not $repo) { $repo = Get-Cfg -Config $cfg -Section 'dataset' -Key 'repo_id' }

$datasetRoot = $Root
if (-not $datasetRoot) { $datasetRoot = Get-DatasetRoot -Config $cfg -RepoId $repo }

if (-not (Test-Path -LiteralPath $datasetRoot)) {
    throw "找不到数据集目录：$datasetRoot`n先确认 config\robot.ini 里的 dataset.repo_id / root_dir，或先用 05_record_dataset.ps1 采一段数据。"
}

Write-Head "查看数据集 -> $repo"
Write-Host "  数据目录 : $datasetRoot"
Write-Host "  第几轮   : $Episode"

$argv = @(
    '-m', 'lerobot.scripts.visualize_dataset',
    '--repo-id', $repo,
    '--root', $datasetRoot,
    '--episode-index', "$Episode",
    '--num-workers', "$NumWorkers"
)

$outDir = Join-Path $script:ProjectRoot '_setup\dataset_rrd'
if ($Save) {
    $argv += @('--save', '1', '--output-dir', $outDir)
    Write-Host "  导出到   : $outDir"
}

Invoke-Lerobot -ArgList $argv -DryRun:$DryRun

if ($Save -and -not $DryRun) {
    $name = $repo.Replace('/', '_') + "_episode_$Episode.rrd"
    Write-Host ''
    Write-Host "已导出：$(Join-Path $outDir $name)" -ForegroundColor Green
    Write-Host "打开方式：rerun `"$(Join-Path $outDir $name)`"" -ForegroundColor Green
}
