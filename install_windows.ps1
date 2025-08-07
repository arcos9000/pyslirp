# Python Development Shell
# PowerShell script for installing pyShell

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$InstallPath = "$env:ProgramFiles\PyLiRP",
    
    [Parameter(Mandatory=$false)]
    [string]$ConfigPath = "$env:ProgramData\PyLiRP",
    
    [Parameter(Mandatory=$false)]
    [switch]$InstallService = $true,
    
    [Parameter(Mandatory=$false)]
    [switch]$SetupFirewall = $true,
    
    [Parameter(Mandatory=$false)]
    [switch]$Force = $false
)

# Colors for output
$Red = "Red"
$Green = "Green"
$Yellow = "Yellow"
$Blue = "Cyan"

function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor $Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor $Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor $Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor $Red
}

function Test-AdminPrivileges {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-PythonInstallation {
    Write-Status "Checking Python installation..."
    
    try {
        $pythonVersion = & python --version 2>$null
        if ($pythonVersion -match "Python (\d+)\.(\d+)") {
            $majorVersion = [int]$matches[1]
            $minorVersion = [int]$matches[2]
            
            if ($majorVersion -eq 3 -and $minorVersion -ge 8) {
                Write-Success "Python $pythonVersion found"
                return $true
            } else {
                Write-Error "Python 3.8+ required, found $pythonVersion"
                return $false
            }
        }
    } catch {
        Write-Error "Python not found in PATH"
        Write-Status "Please install Python 3.8+ from https://www.python.org/downloads/"
        return $false
    }
}

function Install-PythonPackages {
    Write-Status "Installing Python packages..."
    
    try {
        # Upgrade pip
        & python -m pip install --upgrade pip
        
        # Install required packages
        & python -m pip install -r requirements.txt
        
        # Install Windows-specific packages
        & python -m pip install pywin32 win10toast wmi psutil
        
        Write-Success "Python packages installed"
        return $true
    } catch {
        Write-Error "Failed to install Python packages: $_"
        return $false
    }
}

function New-Directories {
    Write-Status "Creating directories..."
    
    $directories = @(
        $InstallPath,
        $ConfigPath,
        "$ConfigPath\logs",
        "$env:ProgramData\PyLiRP\data"
    )
    
    foreach ($dir in $directories) {
        if (!(Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Status "Created directory: $dir"
        }
    }
    
    Write-Success "Directories created"
}

function Copy-ApplicationFiles {
    Write-Status "Installing application files..."
    
    try {
        # Copy Python modules
        $pyFiles = Get-ChildItem -Path "*.py"
        foreach ($file in $pyFiles) {
            Copy-Item $file.FullName -Destination $InstallPath -Force
        }
        
        # Copy configuration
        if (Test-Path "config.yaml") {
            Copy-Item "config.yaml" -Destination "$ConfigPath\config.yaml" -Force
        }
        
        # Copy requirements
        if (Test-Path "requirements.txt") {
            Copy-Item "requirements.txt" -Destination $InstallPath -Force
        }
        
        Write-Success "Application files installed"
        return $true
    } catch {
        Write-Error "Failed to copy application files: $_"
        return $false
    }
}

function Set-WindowsFirewall {
    if (-not $SetupFirewall) {
        return $true
    }
    
    Write-Status "Configuring Windows Firewall..."
    
    try {
        # Allow PyLiRP metrics port
        New-NetFirewallRule -DisplayName "PyLiRP-Metrics" -Direction Inbound -Protocol TCP -LocalPort 9090 -Action Allow -ErrorAction SilentlyContinue
        
        # Allow PyLiRP health check port
        New-NetFirewallRule -DisplayName "PyLiRP-Health" -Direction Inbound -Protocol TCP -LocalPort 9091 -Action Allow -ErrorAction SilentlyContinue
        
        Write-Success "Firewall rules configured"
        return $true
    } catch {
        Write-Warning "Failed to configure firewall rules (non-critical): $_"
        return $true
    }
}

function Install-WindowsService {
    if (-not $InstallService) {
        return $true
    }
    
    Write-Status "Installing Windows service..."
    
    try {
        # Create service installation script
        $serviceScript = @"
import sys
import os
sys.path.insert(0, r'$InstallPath')
from windows_support import WindowsServiceHandler
import win32serviceutil

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(WindowsServiceHandler)
"@
        
        $serviceScriptPath = "$InstallPath\service_handler.py"
        $serviceScript | Out-File -FilePath $serviceScriptPath -Encoding UTF8
        
        # Install the service
        & python "$serviceScriptPath" install
        
        Write-Success "Windows service installed"
        return $true
    } catch {
        Write-Error "Failed to install Windows service: $_"
        return $false
    }
}

function New-StartMenuShortcuts {
    Write-Status "Creating Start Menu shortcuts..."
    
    try {
        $startMenuPath = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs"
        $pyLiRPFolder = "$startMenuPath\PyLiRP"
        
        if (!(Test-Path $pyLiRPFolder)) {
            New-Item -ItemType Directory -Path $pyLiRPFolder -Force | Out-Null
        }
        
        # Create shortcuts
        $WshShell = New-Object -comObject WScript.Shell
        
        # Main application shortcut
        $Shortcut = $WshShell.CreateShortcut("$pyLiRPFolder\PyLiRP.lnk")
        $Shortcut.TargetPath = "python.exe"
        $Shortcut.Arguments = "`"$InstallPath\main.py`" --config `"$ConfigPath\config.yaml`""
        $Shortcut.WorkingDirectory = $InstallPath
        $Shortcut.Description = "Python SLiRP PPP Bridge"
        $Shortcut.Save()
        
        # Configuration shortcut
        $Shortcut = $WshShell.CreateShortcut("$pyLiRPFolder\Edit Configuration.lnk")
        $Shortcut.TargetPath = "notepad.exe"
        $Shortcut.Arguments = "`"$ConfigPath\config.yaml`""
        $Shortcut.Description = "Edit PyLiRP Configuration"
        $Shortcut.Save()
        
        # Status shortcut
        $statusScript = @"
@echo off
echo PyLiRP Status Check
echo ==================
sc query PyLiRP
echo.
echo Press any key to exit...
pause > nul
"@
        $statusBat = "$InstallPath\status.bat"
        $statusScript | Out-File -FilePath $statusBat -Encoding ASCII
        
        $Shortcut = $WshShell.CreateShortcut("$pyLiRPFolder\Service Status.lnk")
        $Shortcut.TargetPath = $statusBat
        $Shortcut.Description = "Check PyLiRP Service Status"
        $Shortcut.Save()
        
        Write-Success "Start Menu shortcuts created"
        return $true
    } catch {
        Write-Warning "Failed to create Start Menu shortcuts: $_"
        return $true
    }
}

function Set-EnvironmentVariables {
    Write-Status "Setting environment variables..."
    
    try {
        # Set system environment variables
        [Environment]::SetEnvironmentVariable("PYSLIRP_CONFIG_PATH", $ConfigPath, "Machine")
        [Environment]::SetEnvironmentVariable("PYSLIRP_INSTALL_PATH", $InstallPath, "Machine")
        
        Write-Success "Environment variables set"
        return $true
    } catch {
        Write-Warning "Failed to set environment variables: $_"
        return $true
    }
}

function New-WindowsConfiguration {
    Write-Status "Creating Windows-specific configuration..."
    
    $windowsConfig = @"
# Windows-specific PyLiRP Configuration

serial:
  port: COM1  # Change to your COM port
  baudrate: 115200
  flow_control: hardware
  timeout: 5.0
  write_timeout: 2.0

network:
  local_ip: 10.0.0.1
  remote_ip: 10.0.0.2
  mtu: 1500
  netmask: 255.255.255.0

services:
  22:
    host: 127.0.0.1
    port: 22
    name: SSH
    enabled: false  # Enable if SSH server is installed
    
  80:
    host: 127.0.0.1
    port: 80
    name: HTTP
    enabled: true
    
  443:
    host: 127.0.0.1
    port: 443
    name: HTTPS
    enabled: true
    
  3389:
    host: 127.0.0.1
    port: 3389
    name: Remote Desktop
    enabled: true
    max_connections: 5
    
  5900:
    host: 127.0.0.1
    port: 5900
    name: VNC
    enabled: false
    max_connections: 3

logging:
  level: INFO
  file:
    enabled: true
    path: $($ConfigPath.Replace('\', '/'))/logs/pyslirp.log
    max_size: 10MB
    rotate_count: 5
  console:
    enabled: true
    color: true

monitoring:
  enable_metrics: true
  metrics_port: 9090
  health_check:
    enabled: true
    port: 9091

# Windows-specific settings
windows:
  use_event_log: true
  show_notifications: true
  process_priority: high
  optimize_serial: true
"@

    try {
        $configFile = "$ConfigPath\config.yaml"
        if (!(Test-Path $configFile) -or $Force) {
            $windowsConfig | Out-File -FilePath $configFile -Encoding UTF8
            Write-Success "Windows configuration created: $configFile"
        } else {
            Write-Status "Configuration file already exists: $configFile"
        }
        return $true
    } catch {
        Write-Error "Failed to create configuration: $_"
        return $false
    }
}

function Show-PostInstallInfo {
    Write-Success "PyLiRP Windows installation completed!"
    
    Write-Host ""
    Write-Host "=== Installation Summary ===" -ForegroundColor Yellow
    Write-Host "Install Path: $InstallPath"
    Write-Host "Config Path: $ConfigPath"
    Write-Host "Service Installed: $InstallService"
    Write-Host "Firewall Configured: $SetupFirewall"
    
    Write-Host ""
    Write-Host "=== Next Steps ===" -ForegroundColor Yellow
    Write-Host "1. Edit configuration: $ConfigPath\config.yaml"
    Write-Host "2. Set your COM port in the configuration"
    Write-Host "3. Start the service: sc start PyLiRP"
    Write-Host "4. Check status: sc query PyLiRP"
    Write-Host "5. View logs: Get-Content `"$ConfigPath\logs\pyslirp.log`""
    
    Write-Host ""
    Write-Host "=== Available COM Ports ===" -ForegroundColor Yellow
    try {
        $comPorts = Get-WmiObject -Class Win32_SerialPort | Select-Object Name, DeviceID, Description
        if ($comPorts) {
            $comPorts | Format-Table -AutoSize
        } else {
            Write-Host "No COM ports found"
        }
    } catch {
        Write-Host "Could not enumerate COM ports"
    }
    
    Write-Host ""
    Write-Host "=== Service Commands ===" -ForegroundColor Yellow
    Write-Host "Start service:    sc start PyLiRP"
    Write-Host "Stop service:     sc stop PyLiRP"
    Write-Host "Query status:     sc query PyLiRP"
    Write-Host "Remove service:   sc delete PyLiRP"
    
    Write-Host ""
    Write-Host "=== Monitoring ===" -ForegroundColor Yellow
    Write-Host "Metrics:     http://localhost:9090/metrics"
    Write-Host "Health:      http://localhost:9091/health"
    Write-Host "Event Log:   Check Windows Event Viewer -> Application"
    
    Write-Host ""
    Write-Host "=== Configuration ===" -ForegroundColor Yellow
    Write-Host "Remember to:"
    Write-Host "- Set the correct COM port in config.yaml"
    Write-Host "- Configure services you want to expose"
    Write-Host "- Adjust security settings as needed"
    Write-Host "- Test connectivity before deploying"
}

function Test-ComPort {
    param([string]$PortName)
    
    Write-Status "Testing COM port: $PortName"
    
    try {
        # Use Python to test the port
        $testScript = @"
import serial
import sys

try:
    with serial.Serial('$PortName', 115200, timeout=1) as ser:
        print('SUCCESS: COM port $PortName opened successfully')
        sys.exit(0)
except Exception as e:
    print(f'ERROR: Failed to open COM port $PortName: {e}')
    sys.exit(1)
"@
        
        $testResult = $testScript | python -
        if ($LASTEXITCODE -eq 0) {
            Write-Success $testResult
            return $true
        } else {
            Write-Error $testResult
            return $false
        }
    } catch {
        Write-Error "Failed to test COM port: $_"
        return $false
    }
}

# Main installation process
function Main {
    Write-Host "PyLiRP Windows Installation Script" -ForegroundColor Green
    Write-Host "=================================" -ForegroundColor Green
    Write-Host ""
    
    # Check prerequisites
    if (-not (Test-AdminPrivileges)) {
        Write-Error "This script must be run as Administrator"
        Write-Host "Right-click on PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
        exit 1
    }
    
    if (-not (Test-PythonInstallation)) {
        exit 1
    }
    
    # Installation steps
    $steps = @(
        { New-Directories },
        { Install-PythonPackages },
        { Copy-ApplicationFiles },
        { New-WindowsConfiguration },
        { Set-WindowsFirewall },
        { Install-WindowsService },
        { New-StartMenuShortcuts },
        { Set-EnvironmentVariables }
    )
    
    foreach ($step in $steps) {
        if (-not (& $step)) {
            Write-Error "Installation failed at step: $($step.ToString())"
            exit 1
        }
    }
    
    Show-PostInstallInfo
    
    # Offer to test COM port
    Write-Host ""
    $testCom = Read-Host "Would you like to test a COM port? (y/N)"
    if ($testCom -eq 'y' -or $testCom -eq 'Y') {
        $comPort = Read-Host "Enter COM port name (e.g., COM1)"
        if ($comPort) {
            Test-ComPort $comPort
        }
    }
    
    Write-Host ""
    Write-Success "Installation completed successfully!"
}

# Run main installation if script is executed directly
if ($MyInvocation.InvocationName -eq $MyInvocation.MyCommand.Path) {
    Main
}