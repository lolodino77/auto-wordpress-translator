@echo off
rem Traducteur d'articles, VERSION PORTABLE pour Windows : ce fichier est le seul a double-cliquer.
rem - deja pret : ouvre le Traducteur tout de suite (sans fenetre noire) ;
rem - premiere fois, nouvelle version ou dossier deplace : prepare d'abord le programme dans ce dossier
rem   (outil "uv", Python, bibliotheques, navigateur), via programme\packaging\common\prepare.py.
rem Rien n'est installe ailleurs sur l'ordinateur : desinstaller = supprimer ce dossier.
rem Variables facultatives (tests) : TRADUCTEUR_OPTIONS, TRADUCTEUR_SANS_LANCEMENT, TRADUCTEUR_AUTOMATIQUE (pas de pause).
chcp 65001 >nul
setlocal EnableExtensions
title Traducteur d'articles
cd /d "%~dp0"
set "P=%~dp0programme"

if exist "%P%\packaging\common\prepare.py" goto :trouve
echo.
echo   Le dossier "programme" est introuvable a cote de ce fichier.
echo   Le fichier .zip n'a sans doute pas ete decompresse :
echo     1. clic droit sur le fichier .zip, puis "Extraire tout...", puis "Extraire" ;
echo     2. dans le dossier extrait, double-cliquez sur "Ouvrir le Traducteur".
goto :echec
:trouve

rem --- Deja pret ? (verification rapide) : ouverture immediate.
if not exist "%P%\.venv\Scripts\python.exe" goto :preparer
"%P%\.venv\Scripts\python.exe" "%P%\packaging\common\prepare.py" --root "%P%" --check >nul 2>&1
if errorlevel 1 goto :preparer
goto :ouvrir

:preparer
echo.
echo   ==========================================================
echo     Traducteur d'articles : preparation du programme
echo     Gardez cette fenetre ouverte jusqu'a la fin.
echo   ==========================================================
set "UV=%P%\runtime\uv.exe"
if exist "%UV%" goto :uv_ok
echo.
echo   Telechargement de l'outil de preparation...
set "RUNTIME=%P%\runtime"
set "UV_ARCH=x86_64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "UV_ARCH=aarch64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "UV_ARCH=aarch64"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; New-Item -ItemType Directory -Force -Path $env:RUNTIME | Out-Null; $z=Join-Path $env:TEMP 'uv-traducteur.zip'; $t=Join-Path $env:TEMP 'uv-traducteur'; Invoke-WebRequest -UseBasicParsing -Uri ('https://github.com/astral-sh/uv/releases/latest/download/uv-' + $env:UV_ARCH + '-pc-windows-msvc.zip') -OutFile $z; if (Test-Path $t) { Remove-Item -Recurse -Force $t }; Expand-Archive -Force -Path $z -DestinationPath $t; Copy-Item -Force (Get-ChildItem -Path $t -Recurse -Filter 'uv.exe' | Select-Object -First 1).FullName (Join-Path $env:RUNTIME 'uv.exe'); Remove-Item -Recurse -Force $t, $z"
if errorlevel 1 goto :echec_reseau
if not exist "%UV%" goto :echec_reseau
:uv_ok
set "UV_PYTHON_INSTALL_DIR=%P%\runtime\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_SYSTEM_CERTS=1"
set "UV_LINK_MODE=copy"
"%UV%" run --no-project --python 3.12 "%P%\packaging\common\prepare.py" --root "%P%" --uv "%UV%" %TRADUCTEUR_OPTIONS%
if errorlevel 1 goto :echec

:ouvrir
if defined TRADUCTEUR_SANS_LANCEMENT exit /b 0
start "" /d "%P%" "%P%\.venv\Scripts\pythonw.exe" -m webapp
exit /b 0

:echec_reseau
echo.
echo   Impossible de telecharger l'outil de preparation.
echo   Verifiez la connexion Internet, puis relancez ce fichier.
:echec
echo.
echo   La preparation n'a pas abouti : le message ci-dessus indique pourquoi.
echo   Vous pouvez relancer ce fichier : elle reprendra sans rien perdre.
if not defined TRADUCTEUR_AUTOMATIQUE pause
exit /b 1
