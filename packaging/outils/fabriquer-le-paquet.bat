@echo off
rem Fabrique dist\TraducteurWordPress-<Systeme>.zip (a envoyer aux coequipiers). Outil du developpeur, sous Windows :
rem appele par "Fabriquer le paquet Windows.bat" et "Fabriquer le paquet Linux.bat" (racine du projet), jamais embarque.
rem   %1 = windows ou linux (packaging\<systeme>\system.py)   %2 = Windows ou Linux (nom du paquet)
rem Etapes : 1) reconstruit l'interface  2) fait suivre par git les fichiers nouveaux  3) fabrique le .zip.
chcp 65001 >nul
setlocal EnableExtensions
set "SYSTEME=%~1"
set "NOM=%~2"
if "%SYSTEME%"=="" goto :usage
if "%NOM%"=="" goto :usage
title Fabrication du paquet %NOM%
cd /d "%~dp0..\.."
set "COPIE=dist\TraducteurWordPress-%NOM%"

echo.
echo  === Fabrication du paquet %NOM% ===
echo.

rem --- Python : .venv, sinon l'environnement conda du projet --------------------------------------------------
set "PY="
if exist "%CD%\.venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
set "ENVNAME=auto-wordpress-translator"
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\miniforge3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3") do (
  if not defined PY if exist "%%~D\envs\%ENVNAME%\python.exe" set "PY=%%~D\envs\%ENVNAME%\python.exe"
)
if not defined PY (
  echo  Python introuvable : lancez d'abord setup_env.ps1 pour creer l'environnement %ENVNAME%.
  goto :echec
)

where git >nul 2>nul
if errorlevel 1 (
  echo  Git est introuvable : installez-le puis reessayez.
  goto :echec
)

rem --- 1) Interface ---------------------------------------------------------------------------------------------
where npm >nul 2>nul
if errorlevel 1 (
  echo  Node.js est introuvable : installez-le depuis nodejs.org puis reessayez.
  goto :echec
)
echo  [1/3] Reconstruction de l'interface...
pushd frontend
if not exist node_modules (
  echo        Installation des dependances de l'interface ^(premiere fois, quelques minutes^)...
  call npm ci
  if errorlevel 1 ( popd & goto :echec )
)
call npm run build
if errorlevel 1 ( popd & goto :echec )
popd

rem --- 2) git : seuls les fichiers suivis sont embarques (sans commiter) ------------------------------------------
echo.
echo  [2/3] Prise en compte des fichiers nouveaux ou modifies...
git add -A webapp packaging frontend *.py config.toml README.md
if errorlevel 1 goto :echec

rem --- Ancienne copie dezippee (dossier d'essai) : supprimee de force, pour ne jamais tester une vieille version ----
if not exist "%COPIE%\" goto :apres_suppression
echo.
echo  Suppression de l'ancienne copie dezippee : %COPIE%
rem Le Traducteur (ou son navigateur) de cette copie est peut-etre encore ouvert : on l'arrete d'abord, sinon Windows
rem refuse de supprimer ses fichiers.
powershell -NoProfile -Command "$d=(Resolve-Path $env:COPIE).Path; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and (($_.ExecutablePath -and $_.ExecutablePath.StartsWith($d,[StringComparison]::OrdinalIgnoreCase)) -or ($_.CommandLine -and $_.CommandLine.IndexOf($d,[StringComparison]::OrdinalIgnoreCase) -ge 0)) } | ForEach-Object { Write-Host ('  Arret de ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
ping -n 3 127.0.0.1 >nul
rmdir /s /q "%COPIE%" 2>nul
if not exist "%COPIE%\" goto :apres_suppression
ping -n 4 127.0.0.1 >nul
rmdir /s /q "%COPIE%"
if exist "%COPIE%\" (
  echo  Impossible de la supprimer : fermez les fenetres qui utilisent ce dossier ^(explorateur, terminal^), puis reessayez.
  goto :echec
)
:apres_suppression

rem --- 3) Paquet --------------------------------------------------------------------------------------------------
echo.
echo  [3/3] Fabrication du paquet...
"%PY%" packaging\build_package.py %SYSTEME%
if errorlevel 1 goto :echec

echo.
echo  Termine. Le paquet est dans le dossier "dist" :
echo    %COPIE%.zip
echo  Pensez a le tester dans un dossier d'essai avant de l'envoyer.
echo.
if exist "%COPIE%.zip" start "" explorer /select,"%CD%\%COPIE%.zip"
pause
exit /b 0

:usage
echo  Usage : fabriquer-le-paquet.bat windows Windows   (ou : linux Linux)
:echec
echo.
echo  La fabrication du paquet a echoue : voir le message ci-dessus.
echo.
pause
exit /b 1
