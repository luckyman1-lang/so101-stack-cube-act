# ============================================================
#  校准体检：检查两个臂的校准文件是否合理
#
#  为什么需要：偶发的通信错读会返回超出 12 位编码范围(0~4095)的值，
#  一旦被 min/max 记住，该关节的校准跨度就会虚高 —— 归一化后行程被压缩，
#  表现出来就是"遥操作时某个关节几乎不动"。所以每次校准后值得体检一次。
#
#  用法：
#     powershell -ExecutionPolicy Bypass -File scripts\check_calibration.ps1
# ============================================================

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$root = Split-Path -Parent $PSScriptRoot
$calRoot = Join-Path $root '_tools\hf-cache\lerobot\calibration'

$targets = @(
    @{ Name = '从臂 SO101Follower (COM11)'; Path = Join-Path $calRoot 'robots\so101_follower\my_follower.json' },
    @{ Name = '主臂 SO101Leader   (COM10)'; Path = Join-Path $calRoot 'teleoperators\so101_leader\my_leader.json' }
)
$joints = @('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')

# 12 位编码：整个行程 4096。正常关节跨度大致在 1000~4000；
# 低于 300 说明基本没被推动，高于 5000 说明掺进了超范围读数。
$MIN_OK = 300
$MAX_OK = 5000

Write-Host ''
$bad = 0

foreach ($t in $targets) {
    Write-Host ('=' * 62) -ForegroundColor Cyan
    Write-Host "  $($t.Name)" -ForegroundColor Cyan
    Write-Host ('=' * 62) -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $t.Path)) {
        Write-Host '  ✗ 校准文件不存在 —— 这个臂还没校准成功过' -ForegroundColor Red
        Write-Host "    $($t.Path)"
        $bad++
        continue
    }

    $json = Get-Content -LiteralPath $t.Path -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host ("  {0,-15} {1,8} {2,8} {3,9}   {4}" -f '关节', 'MIN', 'MAX', '跨度', '判定')
    Write-Host ('  ' + ('-' * 56))

    foreach ($j in $joints) {
        $m = $json.$j
        if ($null -eq $m) { Write-Host ("  {0,-15} (文件里没有这个关节)" -f $j) -ForegroundColor Yellow; continue }
        $span = [int]$m.range_max - [int]$m.range_min
        $verdict = 'OK'
        $color = 'Gray'
        if ($span -gt $MAX_OK) { $verdict = '异常：掺进了超范围读数'; $color = 'Red'; $bad++ }
        elseif ($span -lt $MIN_OK) { $verdict = '异常：基本没推到'; $color = 'Red'; $bad++ }
        Write-Host ("  {0,-15} {1,8} {2,8} {3,9}   {4}" -f $j, $m.range_min, $m.range_max, $span, $verdict) -ForegroundColor $color
    }
    Write-Host ''
}

Write-Host ('=' * 62) -ForegroundColor Cyan
if ($bad -eq 0) {
    Write-Host '  体检通过：所有关节跨度都合理，可以进行遥操作测试。' -ForegroundColor Green
    Write-Host '  下一步： powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1'
}
else {
    Write-Host "  有 $bad 项异常，建议重新校准（按提示把每个关节都推到两端）。" -ForegroundColor Red
    Write-Host '  重新校准： powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1'
}
Write-Host ('=' * 62) -ForegroundColor Cyan
Write-Host ''
