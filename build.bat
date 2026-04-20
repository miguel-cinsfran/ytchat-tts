@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ================================================================
echo   YTChat TTS — Compilar a .exe con PyInstaller
echo  ================================================================
echo.

REM ── Comprobar Python 64 bits ────────────────────────────────────────────────
python -c "import struct; exit(0 if struct.calcsize('P')*8==64 else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Se requiere Python de 64 bits para compilar.
    echo  PyInstaller con Python 32 bits no recogerá las dependencias
    echo  de win32com correctamente.
    echo.
    pause & exit /b 1
)

REM ── Comprobar PyInstaller ────────────────────────────────────────────────────
pyinstaller --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  PyInstaller no encontrado. Instalando...
    pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo  ERROR: No se pudo instalar PyInstaller.
        pause & exit /b 1
    )
)

REM ── Generar sonidos si faltan ────────────────────────────────────────────────
if not exist "sounds\mensaje.wav" (
    echo  Generando sonidos...
    python sound_gen.py
)

REM ── Limpiar builds anteriores ────────────────────────────────────────────────
echo  Limpiando compilaciones anteriores...
if exist "dist\YTChat-TTS" rmdir /s /q "dist\YTChat-TTS"
if exist "build"            rmdir /s /q "build"

echo.
echo  Compilando (esto puede tardar 1-2 minutos)...
echo.

REM ── PyInstaller ─────────────────────────────────────────────────────────────
pyinstaller --noconfirm --clean ytchat.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: La compilacion fallo.
    echo.
    echo  Si ves "ModuleNotFoundError: No module named 'X'", anade
    echo  'X' a la lista hiddenimports en ytchat.spec y vuelve a intentarlo.
    echo.
    pause & exit /b 1
)

REM ── Copiar archivos externos (editables por el usuario) ──────────────────────
echo.
echo  Copiando archivos de usuario a la carpeta de distribucion...
copy /y config.ini   "dist\YTChat-TTS\" >nul
copy /y sounds.ini   "dist\YTChat-TTS\" >nul
copy /y README.md    "dist\YTChat-TTS\" >nul
copy /y instalar.bat "dist\YTChat-TTS\" >nul
xcopy /e /y /i sounds "dist\YTChat-TTS\sounds" >nul

REM ── Resultado ────────────────────────────────────────────────────────────────
echo.
echo  ================================================================
echo   Compilacion completada.
echo.
echo   Carpeta:     dist\YTChat-TTS\
echo   Ejecutable:  dist\YTChat-TTS\YTChat-TTS.exe
echo.
echo   PARA DISTRIBUIR:
echo     Comprime TODA la carpeta dist\YTChat-TTS\ en un ZIP.
echo     El .exe solo no funciona: necesita los archivos que lo rodean.
echo.
echo   PARA PROBAR:
echo     dist\YTChat-TTS\YTChat-TTS.exe
echo  ================================================================
echo.
pause
