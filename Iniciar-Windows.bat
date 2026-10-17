@echo off
chcp 65001 >nul
title Edita Facil
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto sem_python

where ffmpeg >nul 2>nul
if errorlevel 1 goto sem_ffmpeg

if not exist ".venv\Scripts\python.exe" goto instalar
fc /b requirements.txt .venv\instalado.txt >nul 2>nul
if errorlevel 1 goto instalar
goto abrir

:instalar
echo.
echo  Preparando o Edita Facil (so na primeira vez, leva alguns minutos)...
echo.
python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
copy /y requirements.txt .venv\instalado.txt >nul

:abrir
".venv\Scripts\python.exe" -m server
pause
exit /b

:sem_python
echo.
echo  Instalando o Python...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo  Pronto. FECHE esta janela e abra o Iniciar-Windows de novo.
pause
exit /b

:sem_ffmpeg
echo.
echo  Instalando o ffmpeg (programa que monta os videos)...
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
echo.
echo  Pronto. FECHE esta janela e abra o Iniciar-Windows de novo.
pause
exit /b

:erro
echo.
echo  Algo deu errado na instalacao. Tire um print desta tela e me mande.
pause
