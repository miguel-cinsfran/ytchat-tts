@echo off
REM ============================================================================
REM  YTChat TTS - Construye el ejecutable distribuible con PyInstaller (onedir)
REM
REM  Resultado: carpeta "YTChat TTS" en la raiz del proyecto, lista para
REM  comprimir (7-Zip / ZIP) y enviar. Quien la reciba solo descomprime y abre
REM  YTChatTTS.exe; no necesita Python ni nada instalado.
REM
REM  Modo onedir: el .exe queda junto a la carpeta _internal (dependencias) y a
REM  los archivos editables (config.ini, sounds.ini, sounds/). Es mas fiable y
REM  arranca mas rapido que --onefile, y mantiene pocos elementos sueltos.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 ( echo ERROR: uv no esta instalado. Ver README. & pause & exit /b 1 )

echo == Preparando entorno (uv) ==
call uv venv
if errorlevel 1 ( echo ERROR creando el entorno. & pause & exit /b 1 )
call uv pip install -r requirements.txt
if errorlevel 1 ( echo ERROR instalando dependencias. & pause & exit /b 1 )
call uv pip install pyinstaller
if errorlevel 1 ( echo ERROR instalando PyInstaller. & pause & exit /b 1 )

echo == Generando los sonidos ==
call uv run python sound_gen.py >nul

echo == Localizando el discovery doc de YouTube (solo ese, no el cache entero) ==
for /f "delims=" %%i in ('uv run python -c "import googleapiclient,os;print(os.path.join(os.path.dirname(googleapiclient.__file__),'discovery_cache','documents','youtube.v3.json'))"') do set "YTDOC=%%i"
echo    %YTDOC%

REM Icono opcional: si dejas un app.ico en la raiz, se usa para el .exe.
set "ICONO="
if exist "app.ico" set "ICONO=--icon app.ico"

echo == Empaquetando con PyInstaller ==
REM --noupx: NO comprimir con UPX. UPX dispara muchos falsos positivos de
REM antivirus; sin el, el .exe levanta menos sospechas en el PC del amigo.
call uv run pyinstaller main.py ^
  --name YTChatTTS ^
  --onedir --windowed --noconfirm --clean --noupx ^
  --distpath dist --workpath build --specpath build ^
  %ICONO% ^
  --collect-all accessible_output2 ^
  --collect-submodules googleapiclient ^
  --collect-submodules google_auth_oauthlib ^
  --collect-submodules pytchat ^
  --add-data "!YTDOC!;googleapiclient/discovery_cache/documents"
if errorlevel 1 ( echo ERROR en PyInstaller. & pause & exit /b 1 )

echo == Ensamblando la carpeta distribuible ==
set "OUT=YTChat TTS"
if exist "%OUT%" rmdir /s /q "%OUT%"

REM robocopy devuelve codigos ^>=1 incluso en exito; no encadenamos errorlevel.
robocopy "dist\YTChatTTS" "%OUT%" /E /NFL /NDL /NJH /NJS /NP >nul
robocopy "sounds" "%OUT%\sounds" /E /NFL /NDL /NJH /NJS /NP >nul
robocopy "docs"   "%OUT%\docs"   /E /NFL /NDL /NJH /NJS /NP >nul
copy /y "config.ini" "%OUT%\" >nul
copy /y "sounds.ini" "%OUT%\" >nul
copy /y "README.md"  "%OUT%\" >nul
copy /y "LICENSE"    "%OUT%\" >nul

REM Por higiene: nada de log ni credenciales en el paquete que se envia.
del /q "%OUT%\ytchat.log" 2>nul
del /q "%OUT%\credenciales.json" 2>nul

echo == Comprimiendo a "%OUT%.zip" ==
if exist "%OUT%.zip" del /q "%OUT%.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%OUT%' -DestinationPath '%OUT%.zip' -Force"

echo.
echo ============================================================================
echo  Listo.
echo    Carpeta: "%OUT%"        (para probar: "%OUT%\YTChatTTS.exe")
echo    ZIP    : "%OUT%.zip"    (esto es lo que mandas al amigo)
echo  El amigo solo descomprime y abre YTChatTTS.exe; no necesita nada mas.
echo ============================================================================
pause
