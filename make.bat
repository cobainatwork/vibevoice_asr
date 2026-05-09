@echo off
REM cmd.exe wrapper that forwards args to make.ps1
REM Usage: make setup, make up, make down, ...
REM (If you have GNU make installed elsewhere, that may take precedence in PATH.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make.ps1" %*
