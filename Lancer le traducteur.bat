@echo off
chcp 65001 >nul
title Traducteur d'articles
cd /d "%~dp0"
rem Double-clic : ouvre l'interface du traducteur dans le navigateur. Fermer cette fenetre arrete le programme.
rem Python : celui installe a cote (installateur Windows, dossier .venv), sinon l'environnement conda (developpement).

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if defined PY goto :lancer

set "ENVNAME=auto-wordpress-translator"
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\miniforge3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3") do (
  if not defined PY if exist "%%~D\envs\%ENVNAME%\python.exe" set "PY=%%~D\envs\%ENVNAME%\python.exe"
)
if not defined PY (
  for /f "delims=" %%P in ('conda run -n %ENVNAME% python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
)
if not defined PY (
  echo.
  echo  Le Traducteur n'est pas installe sur cet ordinateur.
  echo  Lancez d'abord "Installer le traducteur" : voir le fichier LISEZ-MOI.
  echo.
  pause
  exit /b 1
)

:lancer
"%PY%" -m webapp
if errorlevel 1 (
  echo.
  echo  Le programme s'est arrete avec une erreur, voir le message ci-dessus.
  pause
)
