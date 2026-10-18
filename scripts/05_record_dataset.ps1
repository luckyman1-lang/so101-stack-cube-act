# ============================================================
#  04 采集数据集（遥操作录制）
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 5 -EpisodeTime 20
#     powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Task "Pick the red cube"
#     powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Resume      接着已有数据集继续录
#     powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -DryRun      只看命令
#
#  录制中的快捷键（键盘焦点要在这个窗口上）：
#     →   提前结束本轮，进入下一轮
#     ←   放弃本轮，重新录这一轮
#     ESC 立即停止整个录制
#
#  录制技巧（官方经验）：
#     * 先录 5 轮熟悉流程，再录正式数据集
#     * 至少 50 个场景、每个位置 10 次；相机固定不动、抓取动作保持一致
#     * "光看相机画面就能完成任务"是一个很好的判断标准
# ============================================================
param(
    [string]$Task = '',
    [int]$Episodes = 0,
    [int]$EpisodeTime = 0,
    [int]$ResetTime = 0,
    [switch]$Resume,
    [switch]$NoRerun,
    [switch]$DryRun
)

. "$PSScriptRoot\_common.ps1"

$cfg = Get-IniConfig

# ---------- 机械臂 ----------
$robotPort = Get-Cfg -Config $cfg -Section 'robot'  -Key 'port'
$robotId   = Get-Cfg -Config $cfg -Section 'robot'  -Key 'id'   -Default 'my_follower'
$telePort  = Get-Cfg -Config $cfg -Section 'teleop' -Key 'port'
$teleId    = Get-Cfg -Config $cfg -Section 'teleop' -Key 'id'   -Default 'my_leader'
Assert-Port -Port $robotPort -Who '从臂([robot] port)'
Assert-Port -Port $telePort  -Who '主臂([teleop] port)'
Assert-Camera -Config $cfg -Who 'front'

$camArg = Get-CameraArg -Config $cfg

# ---------- 数据集 ----------
$repo = Get-Cfg -Config $cfg -Section 'dataset' -Key 'repo_id'
if (-not $repo.Contains('/')) {
    throw "config\robot.ini 里 dataset.repo_id='$repo' 不是 '用户名/数据集名' 两段格式。"
}
$root = Get-DatasetRoot -Config $cfg -RepoId $repo

$taskText = $Task
if (-not $taskText) { $taskText = Get-Cfg -Config $cfg -Section 'dataset' -Key 'single_task' }

$numEpisodes = $Episodes
if ($numEpisodes -le 0) { $numEpisodes = Get-CfgInt -Config $cfg -Section 'dataset' -Key 'num_episodes' -Default 20 }

$epTime = $EpisodeTime
if ($epTime -le 0) { $epTime = Get-CfgInt -Config $cfg -Section 'dataset' -Key 'episode_time_s' -Default 30 }

$rsTime = $ResetTime
if ($rsTime -le 0) { $rsTime = Get-CfgInt -Config $cfg -Section 'dataset' -Key 'reset_time_s' -Default 10 }

$fps        = Get-CfgInt  -Config $cfg -Section 'dataset' -Key 'fps'         -Default 30
$pushHub    = Get-CfgBool -Config $cfg -Section 'dataset' -Key 'push_to_hub' -Default $false
$playSounds = Get-CfgBool -Config $cfg -Section 'dataset' -Key 'play_sounds' -Default $true

# ---------- 目录冲突检查 ----------
# LeRobot 要求数据集目录"不存在"才会新建；已存在必须用 -Resume 继续录。
if ((Test-Path -LiteralPath $root) -and -not $Resume) {
    Write-Host ''
    Write-Host "数据集目录已存在：$root" -ForegroundColor Red
    Write-Host '这通常意味着这个数据集名已经录过了。请二选一：' -ForegroundColor Yellow
    Write-Host '  1) 继续录进这个数据集：加 -Resume 再跑一次' -ForegroundColor Yellow
    Write-Host '  2) 录一个全新的数据集：改 config\robot.ini 里的 dataset.repo_id（例如 pick_cube_v2）' -ForegroundColor Yellow
    Write-Host '  3) 想删掉重录：把上面那个目录删掉再跑' -ForegroundColor Yellow
    throw '数据集目录已存在，已中止。'
}

$display = -not $NoRerun

Write-Head "采集数据集 -> $repo"
Write-Host "  数据落到      : $root"
Write-Host "  任务描述      : $taskText"
Write-Host "  轮数 / 每轮时长: $numEpisodes 轮 / $epTime 秒（整理 $rsTime 秒）"
Write-Host "  相机          : $camArg"
Write-Host "  上传 HF       : $pushHub"
Write-Host ''
Write-Host '  录制按键（键盘焦点必须落在这个窗口上，录制和整理阶段都有效）：' -ForegroundColor Yellow
Write-Host '    →      结束本轮。堆叠完成就按它，别干等；整理阶段按它可以跳过等待' -ForegroundColor Yellow
Write-Host '    ←      放弃本轮，重录（这轮数据会被丢掉）' -ForegroundColor Yellow
Write-Host '    空格   暂停 / 继续。暂停期间不录画面、也不给从臂发指令' -ForegroundColor Yellow
Write-Host '    ESC    停止录制（已录的轮次会保留，下次加 -Resume 可继续录）' -ForegroundColor Yellow
Write-Host ''
Write-Host '  每轮流程：摆好绿块 → 遥操作堆叠 → 按 → 结束 → 整理期把绿块放回标记处' -ForegroundColor Cyan
if ($display) {
  Write-Host '  注意：本机 rerun 可视化在 Vulkan 下会崩溃，建议加 -NoRerun；' -ForegroundColor DarkYellow
  Write-Host '        想确认画面请先单独跑 _setup\preview_cameras.py（管理员权限）。' -ForegroundColor DarkYellow
}

$argv = @('-m', 'lerobot.record')
$argv += Get-RobotArgs  -Config $cfg
$argv += Get-TeleopArgs -Config $cfg
$argv += @(
    "--dataset.repo_id=$repo",
    "--dataset.root=$root",
    "--dataset.single_task=$taskText",
    "--dataset.num_episodes=$numEpisodes",
    "--dataset.episode_time_s=$epTime",
    "--dataset.reset_time_s=$rsTime",
    "--dataset.fps=$fps",
    '--dataset.video=true',
    "--dataset.push_to_hub=$(Format-Bool $pushHub)",
    "--play_sounds=$(Format-Bool $playSounds)",
    "--display_data=$(Format-Bool $display)"
)
if ($Resume) { $argv += '--resume=true' }

Invoke-Lerobot -ArgList $argv -DryRun:$DryRun

if (-not $DryRun) {
    Write-Host ''
    Write-Host '录制结束。下一步：scripts\06_train_act.ps1 开始训练。' -ForegroundColor Green
}
