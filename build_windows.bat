@echo off
setlocal
py -3.11 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name "AIVoiceChangerRTX" --collect-all PySide6 --collect-all shiboken6 --collect-all PySide6.QtWebEngineCore --collect-all PySide6.QtWebEngineWidgets app\main.py
echo.
echo Build finished. EXE: dist\AIVoiceChangerRTX\AIVoiceChangerRTX.exe
pause
