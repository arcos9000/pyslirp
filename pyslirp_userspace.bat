@echo off
REM PyLiRP Windows Userspace Management Script
REM Batch script for managing PyLiRP without admin privileges

setlocal EnableDelayedExpansion

REM Detect installation paths
set PYSLIRP_HOME=%USERPROFILE%\PyLiRP
set PYSLIRP_CONFIG=%APPDATA%\PyLiRP\config.yaml
set PYSLIRP_LOGS=%APPDATA%\PyLiRP\logs

REM Use environment variables if set
if defined PYSLIRP_INSTALL_PATH set PYSLIRP_HOME=%PYSLIRP_INSTALL_PATH%
if defined PYSLIRP_CONFIG_PATH set PYSLIRP_CONFIG=%PYSLIRP_CONFIG_PATH%\config.yaml
if defined PYSLIRP_LOG_PATH set PYSLIRP_LOGS=%PYSLIRP_LOG_PATH%

REM Check if running from install directory
if exist "%~dp0main.py" (
    set PYSLIRP_HOME=%~dp0
)

REM Colors (limited batch support)
set ESC=
set RED=%ESC%[31m
set GREEN=%ESC%[32m
set YELLOW=%ESC%[33m
set BLUE=%ESC%[34m
set RESET=%ESC%[0m

:main
if "%1"=="" goto show_menu
if /i "%1"=="start" goto start_task
if /i "%1"=="stop" goto stop_task
if /i "%1"=="status" goto show_status
if /i "%1"=="install" goto install_task
if /i "%1"=="uninstall" goto uninstall_task
if /i "%1"=="logs" goto show_logs
if /i "%1"=="config" goto edit_config
if /i "%1"=="console" goto run_console
if /i "%1"=="test" goto test_serial
if /i "%1"=="ports" goto list_ports
if /i "%1"=="help" goto show_help

echo Invalid option: %1
goto show_help

:show_menu
echo.
echo PyLiRP Windows Userspace Management
echo ==================================
echo.
echo Options:
echo   start      - Start PyLiRP (scheduled task or manual)
echo   stop       - Stop PyLiRP processes
echo   status     - Show status and task information
echo   install    - Install userspace startup (task/startup/registry)
echo   uninstall  - Remove userspace startup
echo   logs       - View recent logs
echo   config     - Edit configuration
echo   console    - Run in console mode (debug)
echo   test       - Test serial port
echo   ports      - List COM ports
echo   help       - Show this help
echo.
set /p choice="Enter option: "
call :%choice% 2>nul || (
    echo Invalid option: !choice!
    pause
)
goto :eof

:start_task
echo Starting PyLiRP...
echo.

REM Try scheduled task first
schtasks /query /tn "PyLiRP-UserSpace" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Starting scheduled task...
    schtasks /run /tn "PyLiRP-UserSpace"
    if %ERRORLEVEL%==0 (
        echo Scheduled task started successfully
    ) else (
        echo Failed to start scheduled task, trying manual start...
        goto manual_start
    )
) else (
    echo No scheduled task found, starting manually...
    goto manual_start
)

if "%1"=="" pause
goto :eof

:manual_start
echo Starting PyLiRP manually...
cd /d "%PYSLIRP_HOME%"
start /min "PyLiRP" python main.py --config "%PYSLIRP_CONFIG%" --daemon
echo PyLiRP started in background
if "%1"=="" pause
goto :eof

:stop_task
echo Stopping PyLiRP...

REM Stop scheduled task if running
schtasks /query /tn "PyLiRP-UserSpace" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Stopping scheduled task...
    schtasks /end /tn "PyLiRP-UserSpace" >nul 2>&1
)

REM Kill any running PyLiRP processes
echo Terminating PyLiRP processes...
tasklist | findstr /i "python.exe" >nul
if %ERRORLEVEL%==0 (
    for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fi "windowtitle eq PyLiRP*" /fo csv ^| findstr /v "PID"') do (
        taskkill /pid %%i /f >nul 2>&1
    )
    
    REM Broader search for PyLiRP processes
    wmic process where "commandline like '%%main.py%%'" delete >nul 2>&1
    
    echo PyLiRP processes terminated
) else (
    echo No Python processes found
)

if "%1"=="" pause
goto :eof

:show_status
echo PyLiRP Status Information
echo ========================
echo.

REM Installation info
echo Installation Paths:
echo   Home: %PYSLIRP_HOME%
echo   Config: %PYSLIRP_CONFIG%
echo   Logs: %PYSLIRP_LOGS%
echo.

REM Check scheduled task
echo Scheduled Task Status:
schtasks /query /tn "PyLiRP-UserSpace" /fo list 2>nul | findstr /i "TaskName Status"
if %ERRORLEVEL% neq 0 (
    echo   No scheduled task installed
)
echo.

REM Check running processes
echo Running Processes:
set FOUND_PROCESS=0
for /f "tokens=2,8" %%i in ('tasklist /fi "imagename eq python.exe" /fo csv 2^>nul ^| findstr /v "PID"') do (
    echo   Python PID: %%i
    set FOUND_PROCESS=1
)
if !FOUND_PROCESS!==0 echo   No PyLiRP processes running
echo.

REM Check network ports
echo Network Status:
netstat -an | findstr ":9090 " && echo   Metrics port (9090) active
netstat -an | findstr ":9091 " && echo   Health port (9091) active
echo.

REM Check recent logs
if exist "%PYSLIRP_LOGS%\pyslirp.log" (
    echo Recent Log Activity:
    powershell "Get-Content '%PYSLIRP_LOGS%\pyslirp.log' | Select-Object -Last 3"
) else (
    echo   No log file found
)

if "%1"=="" pause
goto :eof

:install_task
echo Installing PyLiRP Userspace Startup
echo ===================================
echo.

echo Available installation methods:
echo 1. Scheduled Task (recommended)
echo 2. Startup Folder
echo 3. Registry Run Key
echo 4. Manual (no automatic startup)
echo.

set /p method="Choose method (1-4): "

if "!method!"=="1" (
    echo Installing as scheduled task...
    cd /d "%PYSLIRP_HOME%"
    python main.py --install-task --config "%PYSLIRP_CONFIG%" --userspace
    if %ERRORLEVEL%==0 (
        echo Scheduled task installed successfully
    ) else (
        echo Failed to install scheduled task
    )
) else if "!method!"=="2" (
    echo Installing to startup folder...
    cd /d "%PYSLIRP_HOME%"
    python -c "
import sys; sys.path.append('.')
from windows_task_scheduler import WindowsStartupManager
from windows_support import WindowsPlatformManager
manager = WindowsStartupManager(WindowsPlatformManager())
success = manager.add_to_startup_folder(r'%PYSLIRP_HOME%\main.py', r'%PYSLIRP_CONFIG%')
print('Success' if success else 'Failed')
"
) else if "!method!"=="3" (
    echo Installing to registry run key...
    cd /d "%PYSLIRP_HOME%"
    python -c "
import sys; sys.path.append('.')
from windows_task_scheduler import WindowsStartupManager  
from windows_support import WindowsPlatformManager
manager = WindowsStartupManager(WindowsPlatformManager())
success = manager.add_to_registry_run(r'%PYSLIRP_HOME%\main.py', r'%PYSLIRP_CONFIG%', True)
print('Success' if success else 'Failed')
"
) else if "!method!"=="4" (
    echo Manual startup selected - no automatic startup configured
) else (
    echo Invalid selection
)

if "%1"=="" pause
goto :eof

:uninstall_task
echo Uninstalling PyLiRP Userspace Startup
echo =====================================

REM Remove scheduled task
schtasks /delete /tn "PyLiRP-UserSpace" /f >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Scheduled task removed
) else (
    echo No scheduled task found
)

REM Remove from startup folder
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PyLiRP.lnk" (
    del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PyLiRP.lnk"
    echo Startup folder shortcut removed
)

REM Remove from registry
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "PyLiRP" /f >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Registry run key removed
)

echo Uninstallation completed

if "%1"=="" pause
goto :eof

:show_logs
echo PyLiRP Logs
echo ===========

if exist "%PYSLIRP_LOGS%\pyslirp.log" (
    echo Recent log entries:
    echo.
    powershell "Get-Content '%PYSLIRP_LOGS%\pyslirp.log' | Select-Object -Last 50"
    echo.
    echo Press F to follow logs (Ctrl+C to stop)...
    set /p follow="Follow logs? (y/N): "
    if /i "!follow!"=="y" (
        powershell "Get-Content '%PYSLIRP_LOGS%\pyslirp.log' -Wait -Tail 10"
    )
) else (
    echo No log file found at: %PYSLIRP_LOGS%\pyslirp.log
    echo.
    echo Expected log locations:
    echo   %PYSLIRP_LOGS%\pyslirp.log
    echo   %PYSLIRP_HOME%\logs\pyslirp.log
)

if "%1"=="" pause
goto :eof

:edit_config
echo Opening configuration file...

if exist "%PYSLIRP_CONFIG%" (
    notepad "%PYSLIRP_CONFIG%"
) else (
    echo Configuration file not found: %PYSLIRP_CONFIG%
    echo.
    echo Creating default configuration...
    if not exist "%~dp0config.yaml" (
        echo Warning: No template config.yaml found in installation directory
    ) else (
        if not exist "%APPDATA%\PyLiRP" mkdir "%APPDATA%\PyLiRP"
        copy "%~dp0config.yaml" "%PYSLIRP_CONFIG%"
        echo Default configuration created
        notepad "%PYSLIRP_CONFIG%"
    )
)

if "%1"=="" pause
goto :eof

:run_console
echo Running PyLiRP in console mode...
echo Press Ctrl+C to stop
echo.

cd /d "%PYSLIRP_HOME%"
python main.py --config "%PYSLIRP_CONFIG%" --debug

if "%1"=="" pause
goto :eof

:test_serial
set /p port="Enter COM port (e.g., COM1): "
if "!port!"=="" (
    echo No port specified
    goto :eof
)

echo Testing serial port !port!...
cd /d "%PYSLIRP_HOME%"
python main.py --test-serial !port!

if "%1"=="" pause
goto :eof

:list_ports
echo Available COM ports:
echo ===================

cd /d "%PYSLIRP_HOME%"
python main.py --list-com-ports

echo.
echo Detailed port information:
wmic path Win32_SerialPort get DeviceID,Name,Description /format:table 2>nul

if "%1"=="" pause
goto :eof

:show_help
echo.
echo PyLiRP Windows Userspace Management Script
echo ==========================================
echo.
echo This script manages PyLiRP without requiring administrator privileges.
echo PyLiRP runs in userspace using scheduled tasks, startup folder, or registry.
echo.
echo Usage: %0 [command]
echo.
echo Commands:
echo   start      Start PyLiRP (task or manual)
echo   stop       Stop all PyLiRP processes
echo   status     Show detailed status information
echo   install    Install userspace startup method
echo   uninstall  Remove all startup methods
echo   logs       View and follow log files
echo   config     Edit configuration file
echo   console    Run PyLiRP in console for debugging
echo   test       Test serial port connectivity
echo   ports      List available COM ports
echo   help       Show this help message
echo.
echo Installation Paths:
echo   Home:   %PYSLIRP_HOME%
echo   Config: %PYSLIRP_CONFIG%
echo   Logs:   %PYSLIRP_LOGS%
echo.
echo Examples:
echo   %0 start
echo   %0 install
echo   %0 logs
echo   %0 console
echo.

if "%1"=="" pause
goto :eof