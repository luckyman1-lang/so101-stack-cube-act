@echo off
rem ============================================================
rem  Optional: start the board automatically at every logon.
rem  Run this ONCE as Administrator (right-click -> Run as admin).
rem
rem  Then the board is always at http://127.0.0.1:8770
rem  and you never have to remember to start it.
rem
rem  To remove it later:
rem    schtasks /Delete /TN "SO101Board" /F
rem ============================================================
setlocal
set TASK=SO101Board
set PYTHON=D:\LeRobot\_tools\python310\python.exe
set SCRIPT=D:\LeRobot\tools\progress_server.py

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [x] This must be run as Administrator.
  echo       Right-click this file - "Run as administrator".
  echo.
  pause
  exit /b 1
)

echo.
echo   Registering logon task "%TASK%" ...
schtasks /Create /TN "%TASK%" /TR "\"%PYTHON%\" \"%SCRIPT%\" --port 8770" /SC ONLOGON /F
if errorlevel 1 (
  echo   [x] Failed to create the task.
) else (
  echo   [ok] Registered. Log off and back on to test.
  echo        Remove with:  schtasks /Delete /TN "%TASK%" /F
  echo.
  echo   Starting it now for this session ...
  schtasks /Run /TN "%TASK%"
)
echo.
pause
