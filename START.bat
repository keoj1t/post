@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
where py >nul 2>nul
if errorlevel 1 goto nopython
py -3.12 -m venv .venv
if errorlevel 1 py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
:run
.venv\Scripts\python.exe -c "import fastapi, uvicorn, rapidfuzz, multipart"
if not errorlevel 1 goto build
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
:build
.venv\Scripts\python.exe build_frontend.py
if errorlevel 1 goto fail
echo Jana Address: http://127.0.0.1:8080
echo Frontend and backend run together. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080
if errorlevel 1 goto fail
exit /b 0
:nopython
echo Python 3 is required. Install Python and run START.bat again.
:fail
echo Startup failed. See the error above.
pause
exit /b 1
