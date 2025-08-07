@echo off
REM PyLiRP Installation Launcher
REM Launches PowerShell installation script with proper execution policy

echo PyLiRP Windows Userspace Installation Launcher
echo ===============================================
echo.

REM Check if PowerShell is available
powershell -Command "Get-Host" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: PowerShell is not available
    echo Please install PowerShell or use Windows PowerShell
    pause
    exit /b 1
)

echo Starting PowerShell installation script...
echo.

REM Launch PowerShell script with bypass execution policy (Virtual Environment version)
powershell -ExecutionPolicy Bypass -File "%~dp0install_windows_venv.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo Installation may have failed. Check the output above for details.
    pause
) else (
    echo.
    echo Installation completed. Press any key to exit.
    pause >nul
)