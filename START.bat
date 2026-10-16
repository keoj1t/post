@echo off
setlocal
cd /d "%~dp0"
set "dockerCommand=docker"
set "dockerDesktop="
set "dockerWait=0"
if not defined JANA_PORT set "JANA_PORT=8080"
if /i "%~1"=="--local" goto local
if not "%~1"=="" if /i not "%~1"=="--docker" goto usage
where docker >nul 2>nul
if not errorlevel 1 goto dockercheck
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "dockerCommand=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" goto dockercheck
if /i "%~1"=="--docker" goto nodocker
echo Docker is not installed. Starting with local Python instead.
echo To require Docker, use START.bat --docker.
goto local
:dockercheck
call "%dockerCommand%" compose version >nul 2>nul
if errorlevel 1 goto nocompose
call "%dockerCommand%" info >nul 2>nul
if not errorlevel 1 goto compose
if defined JANA_DOCKER_DESKTOP if exist "%JANA_DOCKER_DESKTOP%" set "dockerDesktop=%JANA_DOCKER_DESKTOP%"
if not defined dockerDesktop if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "dockerDesktop=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not defined dockerDesktop if exist "%LOCALAPPDATA%\Docker\Docker Desktop.exe" set "dockerDesktop=%LOCALAPPDATA%\Docker\Docker Desktop.exe"
if not defined dockerDesktop goto noengine
echo Starting Docker Desktop. Waiting up to 120 seconds for Docker...
call powershell -NoProfile -Command "Start-Process -FilePath $env:dockerDesktop -WindowStyle Hidden"
if errorlevel 1 goto fail
:waitdocker
call "%dockerCommand%" info >nul 2>nul
if not errorlevel 1 goto compose
set /a dockerWait+=1 >nul
if %dockerWait% GEQ 60 goto dockertimeout
call timeout /t 2 /nobreak >nul
goto waitdocker
:compose
echo Jana Address: http://127.0.0.1:%JANA_PORT%
echo Building and starting frontend and backend with Docker Compose.
echo First build requires internet. Press Ctrl+C to stop the project.
call "%dockerCommand%" compose up --build
if errorlevel 1 goto fail
exit /b 0
:local
if exist ".venv\Scripts\python.exe" goto localrun
where py >nul 2>nul
if errorlevel 1 goto nopython
py -3.12 -m venv .venv
if errorlevel 1 py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
:localrun
.venv\Scripts\python.exe -c "import fastapi, uvicorn, rapidfuzz, multipart"
if not errorlevel 1 goto localbuild
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
:localbuild
.venv\Scripts\python.exe build_frontend.py
if errorlevel 1 goto fail
echo Jana Address: http://127.0.0.1:%JANA_PORT%
echo Frontend and backend run together. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %JANA_PORT%
if errorlevel 1 goto fail
exit /b 0
:nodocker
echo Docker was not found. Install Docker Desktop, then run START.bat again.
echo Alternatively, run START.bat --local.
goto fail
:nocompose
echo Docker Compose is unavailable. Install or update Docker Desktop.
goto fail
:noengine
echo Docker is installed but its engine is not running.
echo Start your Docker engine, then run START.bat again.
goto fail
:dockertimeout
echo Docker did not become ready within 120 seconds.
echo Check Docker Desktop and its WSL or virtualization settings, then retry.
goto fail
:nopython
echo Python 3 is required for local mode. Install Python or use Docker Desktop.
goto fail
:usage
echo Usage: START.bat [--docker ^| --local]
goto fail
:fail
echo Startup failed. See the error above.
if not defined JANA_NO_PAUSE pause
exit /b 1
