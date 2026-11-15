@echo off
chcp 65001 >nul
title Traducteur d'articles
cd /d "%~dp0"
rem Double-clic : ouvre l'interface du traducteur dans le navigateur. Fermer cette fenetre arrete le programme.

set "ENVNAME=auto-wordpress-translator"
set "PY="
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\miniforge3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3") do (
  if not defined PY if exist "%%~D\envs\%ENVNAME%\python.exe" set "PY=%%~D\envs\%ENVNAME%\python.exe"
)
if not defined PY (
  for /f "delims=" %%P in ('conda run -n %ENVNAME% python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
)
if not defined PY (
  echo.
  echo  L'environnement "%ENVNAME%" est introuvable.
  echo  Faites d'abord l'installation : voir le fichier README.md, partie Installation.
  echo.
  pause
  exit /b 1
)

"%PY%" -m webapp
if errorlevel 1 (
  echo.
  echo  Le programme s'est arrete avec une erreur, voir le message ci-dessus.
  pause
)
