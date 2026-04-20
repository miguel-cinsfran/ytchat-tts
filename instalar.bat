@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ================================================================
echo   YTChat TTS — Instalación
echo  ================================================================
echo.

REM ── Comprobar Python ────────────────────────────────────────────────────────
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Python no encontrado.
    echo.
    echo  Instala Python 3.11 o superior de 64 bits desde:
    echo    https://www.python.org/downloads/
    echo.
    echo  Asegurate de marcar "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

REM Advertir si es Python de 32 bits (SAPI5 no ve las voces modernas en 32 bits)
python -c "import struct; exit(0 if struct.calcsize('P')*8==64 else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  AVISO: Estas usando Python de 32 bits.
    echo  Las voces SAPI5 modernas de Windows 10/11 no son visibles
    echo  con Python de 32 bits. Se recomienda reinstalar Python 64 bits.
    echo.
    pause
)

REM ── Instalar dependencias ────────────────────────────────────────────────────
echo  Instalando dependencias...
echo.
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: La instalacion de dependencias fallo.
    echo  Revisa tu conexion a internet e intentalo de nuevo.
    echo.
    pause
    exit /b 1
)

echo.
echo  ================================================================
echo   Sobre pytchat
echo  ================================================================
echo.
echo  La libreria pytchat puede tener dificultades con algunos tipos
echo  de directos (sin listar, con restricciones de edad, etc.).
echo.
echo  Si tienes problemas de conexion, existe un fork alternativo de
echo  la comunidad que suele resolver estos casos.
echo.
set /p FORK="  ^¿Instalar la version alternativa de pytchat? (s/N): "
if /i "!FORK!"=="s" (
    echo.
    echo  Instalando fork alternativo...
    pip install git+https://github.com/KaitoCross/pytchat.git
    if %ERRORLEVEL% neq 0 (
        echo  No se pudo instalar el fork. Continuando con la version oficial.
    ) else (
        echo  Fork instalado correctamente.
    )
)

REM ── Generar sonidos ─────────────────────────────────────────────────────────
echo.
echo  Generando sonidos de retroalimentacion...
python sound_gen.py
if %ERRORLEVEL% neq 0 (
    echo  AVISO: No se pudieron generar los sonidos.
    echo  La aplicacion funcionara sin ellos.
)

echo.
echo  ================================================================
echo   Instalacion completada.
echo  ================================================================
echo.
echo  Para verificar que las voces estan disponibles:
echo    python -c "import win32com.client; v=win32com.client.Dispatch('SAPI.SpVoice'); print(v.GetVoices().Count, 'voz/voces encontradas')"
echo.

REM ── Ofrecer lanzar la aplicacion ────────────────────────────────────────────
set /p INICIAR="  ^¿Iniciar YTChat TTS ahora? (S/n): "
if /i "!INICIAR!"=="n" goto :fin

echo.
echo  Iniciando YTChat TTS...
start "" python main.py
goto :fin

:fin
echo.
pause
