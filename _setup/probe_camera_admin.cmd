@echo off
rem ============================================================
rem  Double-click this file to probe the Orbbec Gemini 2 camera.
rem  It will raise a UAC prompt -- click "Yes".
rem
rem  Why elevated: the camera's UVC control channel is blocked for
rem  normal users (E_ACCESSDENIED / HResult 0x80070005).
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','%~dp0probe_camera_admin.ps1'"
