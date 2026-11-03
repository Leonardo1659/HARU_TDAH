@echo off
chcp 65001 >nul
title Instalador Ligero - Asistente Educativo Haru (TDAH)
cd /d "%~dp0"

echo ======================================================================
echo   UNIVERSIDAD SALESIANA DE BOLIVIA - PROYECTO INTEGRADOR HARU (TDAH)
echo   Instalando paquetes modernos y ligeros (sin compiladores C++)...
echo ======================================================================
echo.

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
) else (
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PY_CMD=py
    ) else (
        echo [ERROR] No se detecto Python instalado en esta computadora.
        echo Instala Python 3.11 o 3.12 desde python.org marcando "Add Python to PATH".
        pause
        exit /b 1
    )
)

echo [1/2] Instalando interfaz CustomTkinter, Voz Neuronal, Microfono, Arduino y Camara...
%PY_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [AVISO] Hubo un inconveniente al descargar algun paquete. Verifica tu conexion a internet.
    pause
    exit /b 1
)

echo.
echo [2/2] Ejecutando verificacion rapida de modulos...
%PY_CMD% tools\diagnostico.py --rapido

echo.
echo ======================================================================
echo   ¡INSTALACION COMPLETADA CON EXITO!
echo   Haz doble clic en INICIAR_HARU.vbs (o INICIAR_HARU.bat) para abrir
echo   la tableta educativa de Haru sin ventana de terminal.
echo ======================================================================
pause
