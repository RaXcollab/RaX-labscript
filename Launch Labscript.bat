@echo off
setlocal enabledelayedexpansion
title Labscript Launcher
color 0A
del "%TEMP%\lab_pane*.tmp" >nul 2>&1

set "LABSCRIPT_ENV=%~1"
if not defined LABSCRIPT_ENV set "LABSCRIPT_ENV=labscript"

:: Locate conda without assuming a distribution name or user profile, so this
:: launcher works on any collaborator's fork. First hit wins.
set "CONDA_BASE="
if defined CONDA_EXE for %%I in ("%CONDA_EXE%") do for %%J in ("%%~dpI..") do set "CONDA_BASE=%%~fJ"
if not defined CONDA_BASE (
  for %%C in ("%USERPROFILE%\miniconda" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%USERPROFILE%\Miniforge3" "C:\ProgramData\miniconda3" "C:\ProgramData\anaconda3") do (
    if exist "%%~C\shell\condabin\conda-hook.ps1" if not defined CONDA_BASE set "CONDA_BASE=%%~C"
  )
)
if not defined CONDA_BASE (
  color 0C
  echo.
  echo   [!] ERROR: no conda installation found.
  echo       Looked at CONDA_EXE and the usual install locations.
  echo       Install conda, or set CONDA_EXE to its conda.exe and retry.
  echo.
  pause
  exit /b 1
)

:: Write per-pane scripts to avoid escaping hell
(
:: For per-tab title echo $Host.UI.RawUI.WindowTitle='BLACS'
echo ^& "%CONDA_BASE%\shell\condabin\conda-hook.ps1"
echo conda activate %LABSCRIPT_ENV%
echo New-Item -Path "$env:TEMP\lab_pane1.tmp" -Force ^| Out-Null
echo Write-Host ' [OK] BLACS starting...' -ForegroundColor Green
echo blacs
) > "%TEMP%\blacs_start.ps1"

(
:: echo $Host.UI.RawUI.WindowTitle='RUNMANAGER'
echo ^& "%CONDA_BASE%\shell\condabin\conda-hook.ps1"
echo conda activate %LABSCRIPT_ENV%
echo New-Item -Path "$env:TEMP\lab_pane2.tmp" -Force ^| Out-Null
echo Write-Host ' [OK] RUNMANAGER starting...' -ForegroundColor Magenta
echo runmanager
) > "%TEMP%\runmanager_start.ps1"

(
:: echo $Host.UI.RawUI.WindowTitle='LYSE'
echo ^& "%CONDA_BASE%\shell\condabin\conda-hook.ps1"
echo conda activate %LABSCRIPT_ENV%
echo New-Item -Path "$env:TEMP\lab_pane3.tmp" -Force ^| Out-Null
echo Write-Host ' [OK] LYSE starting...' -ForegroundColor Yellow
echo lyse
) > "%TEMP%\lyse_start.ps1"

echo ==================================================
echo                 LABSCRIPT LAUNCHER
echo ==================================================
echo   Environment: %LABSCRIPT_ENV%
echo.

start "" wt -w -1 --pos 1280,50 ^
  new-tab --title "Labscript Suite" pwsh -NoProfile -NoExit -File "%TEMP%\blacs_start.ps1" ^
  ; split-pane -V --title "Labscript Suite" pwsh -NoProfile -NoExit -File "%TEMP%\runmanager_start.ps1" ^
  ; split-pane -H --title "Labscript Suite" pwsh -NoProfile -NoExit -File "%TEMP%\lyse_start.ps1"

echo   Status: Booting Windows Terminal...
echo.

:: 3. The Monitoring Loop
set /a "timer=0"
set /a "timeout_limit=30"

:MONITOR
set /a "progress=0"
if exist "%TEMP%\lab_pane1.tmp" set /a "progress+=1"
if exist "%TEMP%\lab_pane2.tmp" set /a "progress+=1"
if exist "%TEMP%\lab_pane3.tmp" set /a "progress+=1"

:: Visual Bar Logic
set "bar=[----------]"
if %progress% equ 1 set "bar=[###-------]"
if %progress% equ 2 set "bar=[######----]"
if %progress% equ 3 set "bar=[##########]"

cls
echo ==================================================
echo       LABSCRIPT CONTROL DASHBOARD
echo ==================================================
echo.
echo   [SYSTEM STATUS]
echo   Progress: %bar% (%progress%/3 Panes)
echo   Waiting:  %timer%/%timeout_limit% seconds
echo.
echo   Loading profiles and environments...

if %progress% equ 3 goto :SUCCESS
if %timer% geq %timeout_limit% goto :FAIL

timeout /t 1 >nul
set /a "timer+=1"
goto :MONITOR

:FAIL
color 0C
echo.
echo   [!] ERROR: Environment Load Timeout.
echo       Check the Terminal for Conda or Path errors.
echo.
pause
goto :CLEANUP

:SUCCESS
echo.
echo   [+] SUCCESS: All Labscript modules are live.
echo      Cleaning up...
:CLEANUP
del "%TEMP%\lab_pane*.tmp" >nul 2>&1
timeout /t 2 >nul
exit
