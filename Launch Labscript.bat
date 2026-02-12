@echo off
setlocal enabledelayedexpansion
title Labscript Launcher
color 0A

:: 1. Cleanup old session flags
del "%TEMP%\lab_pane*.tmp" >nul 2>&1

echo ==================================================
echo                 LABSCRIPT LAUNCHER
echo ==================================================
echo.

:: 2. Launch Windows Terminal with robust PowerShell syntax
set "INIT_CONDA=& '%USERPROFILE%\miniconda\shell\condabin\conda-hook.ps1'"

:: Open window to the right on a 1440p monitor
start "" wt -w -1 --pos 1280,50 ^
  new-tab pwsh -NoProfile -NoExit -Command "%INIT_CONDA% && conda activate labscript && New-Item -Path \"$env:TEMP\lab_pane1.tmp\" -Force | Out-Null && Write-Host ' [OK] BLACS starting...' -ForegroundColor Green && blacs" ^
  ; split-pane -V pwsh -NoProfile -NoExit -Command "%INIT_CONDA% && conda activate labscript && New-Item -Path \"$env:TEMP\lab_pane2.tmp\" -Force | Out-Null && Write-Host ' [OK] RUNMANAGER starting...' -ForegroundColor Magenta && runmanager" ^
  ; split-pane -H pwsh -NoProfile -NoExit -Command "%INIT_CONDA% && conda activate labscript && New-Item -Path \"$env:TEMP\lab_pane3.tmp\" -Force | Out-Null && Write-Host ' [OK] LYSE starting...' -ForegroundColor Yellow && lyse"

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