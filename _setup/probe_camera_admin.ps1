# ============================================================
#  相机探测（必须管理员运行）
#
#  为什么需要管理员：Orbbec Gemini 2 的 UVC 控制通道对普通用户
#  是封的。普通权限下能"枚举到 1 个设备"，但一读设备信息/开流
#  就抛 E_ACCESSDENIED (0x80070005)：
#     MFCreateDeviceSource(...) returned: HResult 0x80070005
#
#  用法：双击同目录的 probe_camera_admin.cmd（会弹 UAC，点是）
# ============================================================
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'D:\LeRobot'

$py = 'D:\LeRobot\_tools\python310\python.exe'
$probe = 'D:\LeRobot\_setup\cam_probe.py'

Write-Host '============================================' -ForegroundColor Cyan
Write-Host ' Orbbec Gemini 2 探测（管理员）' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan

& $py $probe
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host ">>> 探测成功 (exit=$code)。图和报告在 _setup\cam_snapshots\" -ForegroundColor Green
} else {
    Write-Host ">>> 探测结束但有问题 (exit=$code)。报告见 _setup\cam_snapshots\probe_report.txt" -ForegroundColor Yellow
}
Write-Host '这个窗口留着，可以直接看输出。关掉即可。' -ForegroundColor DarkGray
