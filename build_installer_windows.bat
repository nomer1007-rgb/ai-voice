@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error
pyinstaller --noconfirm --clean --windowed --name RealVoiceAI app\main.py
if errorlevel 1 goto error
where ISCC.exe >nul 2>nul
if errorlevel 1 (
  echo Install Inno Setup 6 first: https://jrsoftware.org/isinfo.php
  pause
  exit /b 2
)
if not exist installer-output mkdir installer-output
ISCC.exe installer\RealVoiceAI.iss
if errorlevel 1 goto error
echo Installer created in installer-output.
pause
exit /b 0
:error
echo BUILD FAILED.
pause
exit /b 1
