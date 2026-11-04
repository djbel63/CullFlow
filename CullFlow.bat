@echo off
setlocal enabledelayedexpansion
title CullFlow ? AI RAW Studio
chcp 65001 >nul 2>&1

echo.
echo  ==============================================================
echo     CullFlow ? The Private AI RAW Culling ^& Studio
echo  ==============================================================
echo.

cd /d "%~dp0"

:: 1. Verificar si existe el entorno virtual
if exist ".venv\Scripts\python.exe" (
    goto :INICIAR
)

:: 2. Si no existe, primera instalación automática
echo  [1/3] Detectando instalación de Python en tu equipo...
set "PY_CMD="

py -3 --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=py -3"
    goto :PYTHON_OK
)

python --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PY_CMD=python"
    goto :PYTHON_OK
)

echo.
echo  [ERROR] No se ha encontrado Python en el sistema.
echo.
echo  Para usar CullFlow necesitas tener instalado Python 3.10 o superior.
echo  Puedes descargarlo gratis en: https://www.python.org/downloads/
echo  (Asegurate de marcar la casilla "Add Python to PATH" durante la instalacion)
echo.
pause
exit /b 1

:PYTHON_OK
echo  [OK] Python detectado: 
!PY_CMD! --version
echo.
echo  [2/3] Creando entorno virtual aislado (.venv)...
!PY_CMD! -m venv .venv
if !errorlevel! neq 0 (
    echo  [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

echo.
echo  [3/3] Instalando dependencias de CullFlow (LibRaw, OpenCV, Torch/IA)...
echo  (Esto solo ocurre la primera vez, tardará un minuto)...
echo.
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo  [ERROR] Hubo un problema instalando los paquetes.
    pause
    exit /b 1
)

echo.
echo  ==============================================================
echo    ¡Instalación completada con éxito! Iniciando CullFlow...
echo  ==============================================================
echo.

:INICIAR
echo  Iniciando estudio CullFlow en segundo plano...
echo  Abriendo tu navegador en http://127.0.0.1:8765
echo.

:: Abrir navegador tras 1.5 segundos
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765"

:: Arrancar el servidor web de CullFlow
.venv\Scripts\python.exe revelar.py web --puerto 8765

if !errorlevel! neq 0 (
    echo.
    echo  El servidor se ha detenido.
    pause
)

