@echo off
setlocal
cd /d "%~dp0\..\.."
python windows\launcher\app_steam.py
if errorlevel 1 pause
