@echo off
title Motor de Leads B2B - Backend (porta 8000)
echo ============================================
echo   Motor de Leads B2B - Backend
echo   Porta: 8000  ^|  Auto-restart: ativo
echo ============================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERRO] venv nao encontrado. Execute:
    echo   py -3.12 -m venv venv
    echo   venv\Scripts\pip.exe install -r requirements.txt
    pause
    exit /b 1
)

venv\Scripts\python.exe start_server.py

pause
