@echo off
rem ============================================================
rem  Double-click to grab one RGB-D snapshot.
rem  UAC prompt will appear -- click Yes.
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','%~dp0snap_rgbd_admin.ps1'"
