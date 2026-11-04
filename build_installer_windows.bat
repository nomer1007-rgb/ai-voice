@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Creating build environment...
py -3.11 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate

echo [2/4] Installing build dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo [3/4] Building Windows application...
pyinstaller --noconfirm --clean --windowed --name AIVoiceChangerRTX --collect-all PySide6 --collect-all shiboken6 --collect-all PySide6.QtWebEngineCore --collect-all PySide6.QtWebEngineWidgets app\main.py
if errorlevel 1 goto error

echo [4/4] Building installer...
where ISCC.exe >nul 2>nul
if errorlevel 1 (
  echo Inno Setup compiler not found.
  echo Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
  echo Then run this file again.
  pause
  exit /b 2
)
if not exist release mkdir release
ISCC.exe installer\AIVoiceChangerRTX.iss
if errorlevel 1 goto error

echo.
echo SUCCESS: release\AI-Voice-Changer-RTX-Setup-v3.exe
pause
exit /b 0

:error
echo.
echo BUILD FAILED. See the error above.
pause
exit /b 1
