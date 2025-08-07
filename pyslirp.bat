@echo off
REM PyLiRP Windows Batch Script
REM Convenient script for running PyLiRP on Windows

setlocal EnableDelayedExpansion

REM Default paths
set PYSLIRP_INSTALL_PATH=%ProgramFiles%\PyLiRP
set PYSLIRP_CONFIG_PATH=%ProgramData%\PyLiRP\config.yaml
set PYSLIRP_LOG_PATH=%ProgramData%\PyLiRP\logs

REM Check if running from install directory
if exist "%~dp0main.py" (
    set PYSLIRP_INSTALL_PATH=%~dp0
)

REM Colors (if supported)
set ESC=
set RED=%ESC%[31m
set GREEN=%ESC%[32m
set YELLOW=%ESC%[33m
set BLUE=%ESC%[34m
set RESET=%ESC%[0m

:main
if "%1"=="" goto show_menu
if /i "%1"=="start" goto start_service
if /i "%1"=="stop" goto stop_service
if /i "%1"=="status" goto show_status
if /i "%1"=="logs" goto show_logs
if /i "%1"=="config" goto edit_config
if /i "%1"=="console" goto run_console
if /i "%1"=="install" goto install_service
if /i "%1"=="uninstall" goto uninstall_service
if /i "%1"=="test" goto test_serial
if /i "%1"=="ports" goto list_ports
if /i "%1"=="help" goto show_help

echo Invalid option: %1
goto show_help

:show_menu
echo.
echo %BLUE%PyLiRP Windows Management Script%RESET%
echo ================================
echo.
echo Options:
echo   start      - Start PyLiRP service
echo   stop       - Stop PyLiRP service  
echo   status     - Show service status
echo   logs       - View recent logs
echo   config     - Edit configuration
echo   console    - Run in console mode
echo   install    - Install Windows service
echo   uninstall  - Uninstall Windows service
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

:start_service
echo %GREEN%Starting PyLiRP service...%RESET%
sc start PyLiRP
if %ERRORLEVEL%==0 (
    echo %GREEN%Service started successfully%RESET%
) else (
    echo %RED%Failed to start service%RESET%
)
if "%1"=="" pause
goto :eof

:stop_service
echo %YELLOW%Stopping PyLiRP service...%RESET%
sc stop PyLiRP
if %ERRORLEVEL%==0 (
    echo %GREEN%Service stopped successfully%RESET%
) else (
    echo %RED%Failed to stop service%RESET%
)
if "%1"=="" pause
goto :eof

:show_status
echo %BLUE%PyLiRP Service Status:%RESET%
echo =====================
sc query PyLiRP
echo.
echo %BLUE%Recent Activity:%RESET%
if exist "%PYSLIRP_LOG_PATH%\pyslirp.log" (
    powershell "Get-Content '%PYSLIRP_LOG_PATH%\pyslirp.log' | Select-Object -Last 5"
) else (
    echo No log file found
)
echo.
echo %BLUE%Network Status:%RESET%
netstat -an | findstr :9090
netstat -an | findstr :9091
if "%1"=="" pause
goto :eof

:show_logs
echo %BLUE%PyLiRP Recent Logs:%RESET%
echo ==================
if exist "%PYSLIRP_LOG_PATH%\pyslirp.log" (
    powershell "Get-Content '%PYSLIRP_LOG_PATH%\pyslirp.log' | Select-Object -Last 50 | Format-Table -Wrap"
    echo.
    echo Press F to follow logs (Ctrl+C to stop)...
    set /p follow="Follow logs? (y/N): "
    if /i "!follow!"=="y" (
        powershell "Get-Content '%PYSLIRP_LOG_PATH%\pyslirp.log' -Wait -Tail 10"
    )
) else (
    echo %RED%No log file found at %PYSLIRP_LOG_PATH%\pyslirp.log%RESET%
)
if "%1"=="" pause
goto :eof

:edit_config
echo %BLUE%Opening configuration file...%RESET%
if exist "%PYSLIRP_CONFIG_PATH%" (
    notepad "%PYSLIRP_CONFIG_PATH%"
) else (
    echo %RED%Configuration file not found: %PYSLIRP_CONFIG_PATH%%RESET%
    echo Creating default configuration...
    if not exist "%ProgramData%\PyLiRP" mkdir "%ProgramData%\PyLiRP"
    copy "%PYSLIRP_INSTALL_PATH%\config.yaml" "%PYSLIRP_CONFIG_PATH%"
    notepad "%PYSLIRP_CONFIG_PATH%"
)
if "%1"=="" pause
goto :eof

:run_console
echo %BLUE%Running PyLiRP in console mode...%RESET%
echo Press Ctrl+C to stop
echo.
cd /d "%PYSLIRP_INSTALL_PATH%"
python main.py --config "%PYSLIRP_CONFIG_PATH%" --debug
if "%1"=="" pause
goto :eof

:install_service
echo %YELLOW%Installing PyLiRP as Windows service...%RESET%
cd /d "%PYSLIRP_INSTALL_PATH%"
python main.py --install-service --config "%PYSLIRP_CONFIG_PATH%"
if %ERRORLEVEL%==0 (
    echo %GREEN%Service installed successfully%RESET%
    echo Starting service...
    sc start PyLiRP
) else (
    echo %RED%Failed to install service%RESET%
)
if "%1"=="" pause
goto :eof

:uninstall_service
echo %YELLOW%Uninstalling PyLiRP Windows service...%RESET%
sc stop PyLiRP
cd /d "%PYSLIRP_INSTALL_PATH%"
python main.py --uninstall-service
if %ERRORLEVEL%==0 (
    echo %GREEN%Service uninstalled successfully%RESET%
) else (
    echo %RED%Failed to uninstall service%RESET%
)
if "%1"=="" pause
goto :eof

:test_serial
set /p port="Enter COM port (e.g., COM1): "
if "!port!"=="" (
    echo %RED%No port specified%RESET%
    goto :eof
)
echo %BLUE%Testing serial port !port!...%RESET%
cd /d "%PYSLIRP_INSTALL_PATH%"
python main.py --test-serial !port!
if "%1"=="" pause
goto :eof

:list_ports
echo %BLUE%Available COM ports:%RESET%
echo ===================
cd /d "%PYSLIRP_INSTALL_PATH%"
python main.py --list-com-ports
echo.
echo %BLUE%Detailed port information:%RESET%
wmic path Win32_SerialPort get DeviceID,Name,Description /format:table
if "%1"=="" pause
goto :eof

:show_help
echo.
echo %BLUE%PyLiRP Windows Management Script%RESET%
echo ================================
echo.
echo Usage: %0 [command]
echo.
echo Commands:
echo   start      Start the PyLiRP service
echo   stop       Stop the PyLiRP service
echo   status     Show service and connection status  
echo   logs       View recent application logs
echo   config     Edit configuration file
echo   console    Run PyLiRP in console mode (for debugging)
echo   install    Install PyLiRP as a Windows service
echo   uninstall  Remove PyLiRP Windows service
echo   test       Test a serial port connection
echo   ports      List available COM ports
echo   help       Show this help message
echo.
echo Examples:
echo   %0 start
echo   %0 logs
echo   %0 console
echo.
echo Configuration: %PYSLIRP_CONFIG_PATH%
echo Install Path:  %PYSLIRP_INSTALL_PATH%
echo Log Path:      %PYSLIRP_LOG_PATH%
echo.
if "%1"=="" pause
goto :eof