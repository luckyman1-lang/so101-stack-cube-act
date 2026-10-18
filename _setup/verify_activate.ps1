# Verify that activate.ps1 works when dot-sourced inside a
# -ExecutionPolicy Bypass process (which is what activate.cmd does).
. 'D:\LeRobot\activate.ps1'

Write-Host ''
Write-Host '--- verification ---'
Write-Host ("python resolves to : " + (Get-Command python -ErrorAction SilentlyContinue).Source)
python -c "import lerobot, sys; print('python version :', sys.version.split()[0]); print('lerobot version:', lerobot.__version__)"
Write-Host ("HF_HOME            : " + $env:HF_HOME)
Write-Host ("HF_LEROBOT_CALIB   : " + $env:HF_LEROBOT_CALIBRATION)
Write-Host ("TEMP               : " + $env:TEMP)
Write-Host ("PYTHONUTF8         : " + $env:PYTHONUTF8)
