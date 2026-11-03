@echo off
chcp 65001 >nul
cd /d "%~dp0"

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "%~dp0haru.pyw"
    exit /b 0
)

where pyw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw "%~dp0haru.pyw"
    exit /b 0
)

echo [ERROR] No se encontro Python en esta computadora.
echo Instala Python 3.11 o superior y ejecuta INSTALAR_DEPENDENCIAS.bat.
pause
