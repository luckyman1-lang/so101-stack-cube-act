@echo off
rem ============================================================
rem  Open a PowerShell window with the LeRobot environment activated.
rem  Double-click this file, or run  D:\LeRobot\activate.cmd
rem
rem  Why this exists: on this machine the PowerShell execution policy
rem  blocks dot-sourcing local .ps1 files directly. Launching a new
rem  PowerShell with -ExecutionPolicy Bypass and dot-sourcing inside it
rem  works, and the env vars stay in that window.
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command ". '%~dp0activate.ps1'"
