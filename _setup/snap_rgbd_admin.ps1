# ============================================================
#  抓一张 RGB-D 快照（必须管理员）
#
#  用法：双击 snap_rgbd_admin.cmd（会弹 UAC，点是）
#        或在管理员 PowerShell 里：
#          & "D:\LeRobot\_tools\python310\python.exe" _setup\snap_rgbd.py --tag green
# ============================================================
param(
    [string]$Tag = 'green',
    [int]$Warmup = 15
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'D:\LeRobot'

Write-Host '============================================' -ForegroundColor Cyan
Write-Host " RGB-D 快照  tag=$Tag" -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan

& 'D:\LeRobot\_tools\python310\python.exe' 'D:\LeRobot\_setup\snap_rgbd.py' --tag $Tag --warmup $Warmup
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host ">>> 成功 (exit=$code)" -ForegroundColor Green
} else {
    Write-Host ">>> 失败 (exit=$code)" -ForegroundColor Yellow
}
