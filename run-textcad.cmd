@echo off
rem ---------------------------------------------------------------------
rem  Start TextCAD Studio on a computer that has never run it.
rem
rem  Double-click this file. It finds Python, installs what is missing the
rem  first time, and starts Studio - which opens a browser tab by itself.
rem  Deliberately dull: no virtualenv, no flags, nothing to get wrong.
rem ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo.
echo   TextCAD Studio
echo   ==============
echo.

rem --- 1. find Python --------------------------------------------------
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo   Python is not installed on this computer, or Windows cannot find it.
  echo.
  echo   Install Python 3.12 or newer from https://www.python.org/downloads/
  echo   In the installer, tick "Add python.exe to PATH".
  echo   Then run this file again.
  echo.
  pause
  exit /b 1
)

for /f "delims=" %%v in ('%PY% --version') do echo   Found %%v

rem --- 2. is it new enough? --------------------------------------------
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 (
  echo.
  echo   That Python is too old - TextCAD needs 3.12 or newer.
  echo   Install a newer one from https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

rem --- 3. install what is missing --------------------------------------
rem  Three imports stand in for the whole list: the geometry kernel and the
rem  web server. If they load, the install already happened.
%PY% -c "import build123d, fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Installing what TextCAD needs. The geometry kernel is a big
  echo   download, so the first run can take several minutes.
  echo.
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo   The install did not finish. The lines above say what went wrong.
    echo.
    pause
    exit /b 1
  )
) else (
  echo   Everything it needs is already installed.
)

rem --- 4. start it -----------------------------------------------------
echo.
echo   Starting TextCAD Studio on http://127.0.0.1:8123
echo   A browser tab opens by itself. Close THIS window to stop Studio.
echo.
%PY% studio.py
echo.
echo   TextCAD Studio has stopped.
pause
