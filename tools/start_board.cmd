@echo off
rem ============================================================
rem  SO-101 project board - double-click to start.
rem
rem  Why you must start it yourself:
rem    This server has to keep running while you and your teammate
rem    work. It cannot be launched by an automated agent, because
rem    those shells kill their whole process tree when the command
rem    returns. So: you start it, and keep the window open.
rem
rem  What it does:
rem    - serves the board on port 8770 (all interfaces)
rem    - opens your browser automatically
rem    - prints the LAN address to give to your teammate
rem
rem  First-run firewall (once, in an ADMIN terminal):
rem    netsh advfirewall firewall add rule name="SO101Board" dir=in action=allow protocol=TCP localport=8770
rem ============================================================
cd /d "%~dp0.."
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul 2>&1

echo.
echo   SO-101 project board
echo   --------------------
echo   Close this window to stop the server.
echo.

"D:\LeRobot\_tools\python310\python.exe" "%~dp0progress_server.py" --port 8770 --open-browser

echo.
echo   Board stopped. Press any key to close.
pause >nul
