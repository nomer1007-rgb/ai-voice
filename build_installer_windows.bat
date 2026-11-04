@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3.11 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1
py -3.11 -m PyInstaller --noconfirm --clean --windowed --name RealVoiceAI --add-data "scripts;scripts" app\main.py
if errorlevel 1 exit /b 1
where ISCC.exe >nul 2>nul
if errorlevel 1 (
  echo Install Inno Setup 6 first: https://jrsoftware.org/isdl.php
  exit /b 1
)
ISCC.exe installer\RealVoiceAI.iss
if errorlevel 1 exit /b 1
echo Installer is in installer-output\RealVoiceAI-Setup-v5.exe
