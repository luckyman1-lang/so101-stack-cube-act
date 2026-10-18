@echo off
rem ============================================================
rem  Open an ELEVATED PowerShell window with the LeRobot env activated.
rem
rem  Why elevated: the Orbbec Gemini 2 camera requires administrator
rem  rights (its USB control channel is blocked for normal users).
rem  Data collection (scripts\05_record_dataset.ps1) needs the camera,
rem  so it must run from an elevated window.
rem
rem  Usage: double-click this file (accept the UAC prompt).
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','%~dp0activate.ps1'"
