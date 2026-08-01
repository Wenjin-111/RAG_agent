@echo off
setlocal enabledelayedexpansion
title Argus Platform

echo ============================================
echo   Argus RAG Platform
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Starting Docker services...

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo   Docker Desktop is not running, attempting to start...

    set "FOUND=0"
    for %%p in (
        "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        "C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe"
    ) do (
        if !FOUND! equ 0 (
            if exist %%p (
                echo   Launching: %%p
                start "Docker Desktop" /B %%p
                set "FOUND=1"
            )
        )
    )

    if !FOUND! equ 0 (
        echo   [FAIL] Docker Desktop.exe not found. Please start it manually.
        pause
        exit /b 1
    )

    echo   Waiting for Docker to be ready...
    :wait_docker
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto wait_docker
    echo   [OK] Docker is ready
)

REM Check for port 5432 conflict (local PostgreSQL service)
netstat -ano | findstr ":5432.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [WARN] Port 5432 is occupied - local PostgreSQL may be running.
    echo   Run as Administrator: net stop postgresql-x64-18
    echo   Then re-run start.bat
    pause
    exit /b 1
)

docker compose down >nul 2>&1
docker rm -f argus-pg argus-minio argus-es >nul 2>&1
docker compose up -d
echo   Waiting for services to be healthy...
timeout /t 10 /nobreak >nul
echo   [OK] Infrastructure running

echo.
echo [2/3] Starting Backend on port 10001...
start "Argus-Backend" cmd /k "cd /d %~dp0Argus-python && conda run -n argus --no-capture-output python -m uvicorn app.main:app --host 0.0.0.0 --port 10001 --reload"

echo.
echo [3/3] Starting Frontend on port 5173...
start "Argus-Frontend" cmd /k "cd /d %~dp0Argus-frontend && npm run dev"

echo.
echo ============================================
echo   Argus Platform Started!
echo.
echo   Frontend : http://localhost:5173
echo   API Docs : http://localhost:10001/docs
echo.
echo   Login    : admin / Admin@123456
echo ============================================
echo.
echo Close the Backend / Frontend windows to stop those services.
echo Run 'docker compose down' to stop the infrastructure.
echo.
pause
