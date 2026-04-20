@echo off
cd /d D:\eai\eai-flow-main\frontend
set PORT=4000
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','D:\eai\eai-flow-main\scripts\frontend-startup.ps1','-Mode','dev' -WindowStyle Hidden"
