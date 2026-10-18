# ============================================================
#  06 用训练好的模型推理：机械臂自主抓取（同时录一份 eval 数据集）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -Path D:\LeRobot\outputs\train\pick_cube\checkpoints\020000\pretrained_model
#     powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -Episodes 5
#     powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -DryRun
#
#  说明：
#   * 只连接从臂，不需要主臂（模型自己出动作）
#   * 数据集名必须以 eval_ 开头（LeRobot 的硬性要求，本脚本会自动补）
#   * 推理效果很吃环境一致性：相机位置、光照（白天/晚上）变化都会明显掉点
# ============================================================
param(
    [string]$Path = '',
    [int]$Episodes = 0,
    [int]$EpisodeTime = 0,
    [int]$ResetTime = 0,
    [string]$RunTag = '',
    [switch]$Fresh,
    [switch]$NoRerun,
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

# ---------- 从臂 ----------
$robotPort = Get-Cfg -Config $cfg -Section 'robot' -Key 'port'
$robotId   = Get-Cfg -Config $cfg -Section 'robot' -Key 'id'   -Default 'my_follower'
Assert-Port -Port $robotPort -Who '从臂([robot] port)'
Assert-Camera -Config $cfg -Who 'front'

# ---------- 模型路径 ----------
$outputDir = Get-Cfg -Config $cfg -Section 'train' -Key 'output_dir' -Default (Join-Path $script:ProjectRoot 'outputs\train\pick_cube')

$policyPath = $Path
if (-not $policyPath) { $policyPath = Get-Cfg -Config $cfg -Section 'policy' -Key 'path' }

if (-not $policyPath) {
    # 自动找 checkpoints 下步数最大的那个
    $ckptRoot = Join-Path $outputDir 'checkpoints'
    if (Test-Path -LiteralPath $ckptRoot) {
        $steps = Get-ChildItem -LiteralPath $ckptRoot -Directory |
            Where-Object { $_.Name -match '^\d+$' } |
            Sort-Object { [int]$_.Name }
        if ($steps.Count -gt 0) {
            $latest = $steps[-1]
            $policyPath = Join-Path $latest.FullName 'pretrained_model'
            Write-Host "自动选用最新 checkpoint：$($latest.Name)" -ForegroundColor Cyan
        }
    }
}

if (-not $policyPath) {
    throw "找不到训练好的模型。请先训练（scripts\06_train_act.ps1），或用 -Path 指定模型目录。"
}
if (-not (Test-Path -LiteralPath $policyPath)) {
    throw "模型路径不存在：$policyPath"
}

# ---------- eval 数据集 ----------
$evalRepo = Get-Cfg -Config $cfg -Section 'policy' -Key 'eval_repo_id' -Default 'local/eval_pick_cube_v1'
if (-not $evalRepo.Contains('/')) {
    throw "config\robot.ini 里 policy.eval_repo_id='$evalRepo' 不是 '用户名/数据集名' 两段格式。"
}

# -RunTag：给这次评测加一个后缀，数据存到独立目录，绝不覆盖之前的。
# 不传 -RunTag 时自动用时间戳，保证每次运行都是新目录。
$runTag = $RunTag
if (-not $runTag) { $runTag = Get-Date -Format 'MMdd_HHmmss' }
if ($evalRepo -notmatch ('_' + [regex]::Escape($runTag) + '$')) {
    $evalRepo = $evalRepo + '_' + $runTag
}

$evalName = $evalRepo.Split('/')[-1]
if (-not $evalName.StartsWith('eval_')) {
    $fixed = $evalRepo.Split('/')[0] + '/eval_' + $evalName
    Write-Host "数据集名必须以 eval_ 开头（LeRobot 要求），已改为：$fixed" -ForegroundColor Yellow
    $evalRepo = $fixed
}
$evalRoot = Get-DatasetRoot -Config $cfg -RepoId $evalRepo -Section 'policy'
Write-Host "本次评测数据存到：$evalRepo（不会覆盖以前的结果）" -ForegroundColor Cyan

if ((Test-Path -LiteralPath $evalRoot)) {
    $parquets = @(Get-ChildItem -LiteralPath $evalRoot -Recurse -Filter '*.parquet' -File -ErrorAction SilentlyContinue)
    if ($Fresh) {
        Write-Host "指定了 -Fresh：删除已有 eval 数据集（$($parquets.Count) 轮）后重跑" -ForegroundColor Yellow
        Remove-Item -LiteralPath $evalRoot -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($parquets.Count -eq 0) {
        # 上次推理失败留下的空壳（没有任何 parquet）直接清掉，免得每次手动删。
        Write-Host "eval 数据集目录是空壳（0 轮数据），自动清理：$evalRoot" -ForegroundColor Yellow
        Remove-Item -LiteralPath $evalRoot -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host ''
        Write-Host "eval 数据集目录已存在，且有 $($parquets.Count) 轮真实数据：$evalRoot" -ForegroundColor Red
        Write-Host '想覆盖重跑就加 -Fresh；想保留就改 config\robot.ini 里的 policy.eval_repo_id。' -ForegroundColor Yellow
        throw 'eval 数据集目录已存在（含真实数据），已中止。'
    }
}

$taskText = Get-Cfg -Config $cfg -Section 'dataset' -Key 'single_task'

$numEpisodes = $Episodes
if ($numEpisodes -le 0) { $numEpisodes = Get-CfgInt -Config $cfg -Section 'policy' -Key 'num_episodes' -Default 10 }
$epTime = $EpisodeTime
if ($epTime -le 0) { $epTime = Get-CfgInt -Config $cfg -Section 'policy' -Key 'episode_time_s' -Default 30 }
# 整理期：每轮结束后给多少秒换绿块的位置。期间模型不输出动作、机械臂不动，
# 按 → 可以提前结束等待，直接开始下一轮。
$rsTime = $ResetTime
if ($rsTime -le 0) { $rsTime = Get-CfgInt -Config $cfg -Section 'policy' -Key 'reset_time_s' -Default 120 }
$fps    = Get-CfgInt -Config $cfg -Section 'dataset' -Key 'fps' -Default 30

$display = -not $NoRerun

Write-Head '模型推理（机械臂自主抓取）'
Write-Host "  模型        : $policyPath"
Write-Host "  从臂        : $robotPort  ($robotId)"
Write-Host "  任务描述    : $taskText"
Write-Host "  eval 数据集 : $evalRepo"
Write-Host "  数据落到    : $evalRoot"
Write-Host "  轮数        : $numEpisodes 轮，每轮最长 $epTime 秒，整理期 $rsTime 秒"
Write-Host ''
Write-Host '  按键：→ 结束本轮 / 跳过整理期   ESC 停止' -ForegroundColor Yellow
Write-Host '  换绿块位置就在「整理期」做：那段时间模型不输出动作，机械臂不动。' -ForegroundColor Yellow
Write-Host '  换好后按 → 立刻开始下一轮，不用等整理期走完。' -ForegroundColor Yellow
Write-Host '  紧急情况随时可以拔电源/按 ESC。' -ForegroundColor Yellow

$argv = @('-m', 'lerobot.record')
$argv += Get-RobotArgs -Config $cfg
$argv += @(
    "--policy.path=$policyPath",
    "--dataset.repo_id=$evalRepo",
    "--dataset.root=$evalRoot",
    "--dataset.single_task=$taskText",
    "--dataset.num_episodes=$numEpisodes",
    "--dataset.episode_time_s=$epTime",
    "--dataset.reset_time_s=$rsTime",
    "--dataset.fps=$fps",
    '--dataset.video=true',
    '--dataset.push_to_hub=false',
    '--play_sounds=false',
    "--display_data=$(Format-Bool $display)"
)

Invoke-Lerobot -ArgList $argv -DryRun:$DryRun
