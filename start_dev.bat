@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\\scripts\\dev.ps1" %*
