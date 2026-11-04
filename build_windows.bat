@echo off
setlocal
py -3.11 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name RealVoiceAI app\main.py
 echo.
echo Build complete: dist\RealVoiceAI\RealVoiceAI.exe
pause
