# PyLiRP Windows Userspace Installation Script
# PowerShell script for installing Python SLiRP without admin privileges

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$InstallMode = "auto",  # auto, portable, user, admin
    
    [Parameter(Mandatory=$false)]
    [string]$InstallPath = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ConfigPath = "",
    
    [Parameter(Mandatory=$false)]
    [string]$StartupMethod = "task",  # task, startup, registry, manual
    
    [Parameter(Mandatory=$false)]
    [switch]$NoAutoStart = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$Force = $false
)

# Check PowerShell execution policy
if ((Get-ExecutionPolicy) -eq "Restricted") {
    Write-Warning "PowerShell execution policy is Restricted"
    Write-Host "Please run the following command to allow script execution:" -ForegroundColor Yellow
    Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Cyan
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne 'y' -and $continue -ne 'Y') {
        exit 1
    }
}

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
    try {
        $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Get-InstallationPaths {
    param(
        [string]$Mode,
        [string]$CustomInstallPath,
        [string]$CustomConfigPath
    )
    
    $hasAdmin = Test-AdminPrivileges
    $paths = @{}
    
    # Determine installation mode
    if ($Mode -eq "auto") {
        if ($hasAdmin) {
            $Mode = "admin"
            Write-Status "Admin privileges detected, using system installation"
        } else {
            $Mode = "user"
            Write-Status "No admin privileges, using user installation"
        }
    }
    
    switch ($Mode) {
        "portable" {
            $baseDir = if ($CustomInstallPath) { $CustomInstallPath } else { Join-Path $PWD "PyLiRP" }
            $paths.InstallDir = $baseDir
            $paths.ConfigDir = Join-Path $baseDir "config"
            $paths.LogDir = Join-Path $baseDir "logs" 
            $paths.DataDir = Join-Path $baseDir "data"
            $paths.Mode = "Portable"
        }
        "user" {
            $homeDir = $env:USERPROFILE
            $appData = $env:APPDATA
            
            $paths.InstallDir = if ($CustomInstallPath) { $CustomInstallPath } else { Join-Path $homeDir "PyLiRP" }
            $paths.ConfigDir = if ($CustomConfigPath) { $CustomConfigPath } else { Join-Path $appData "PyLiRP" }
            $paths.LogDir = Join-Path $appData "PyLiRP\logs"
            $paths.DataDir = Join-Path $appData "PyLiRP\data"
            $paths.Mode = "User"
        }
        "admin" {
            # Only if admin privileges are available
            if (-not $hasAdmin) {
                Write-Warning "Admin mode requested but no admin privileges available, falling back to user mode"
                return Get-InstallationPaths -Mode "user" -CustomInstallPath $CustomInstallPath -CustomConfigPath $CustomConfigPath
            }
            
            $paths.InstallDir = if ($CustomInstallPath) { $CustomInstallPath } else { Join-Path $env:ProgramData "PyLiRP" }
            $paths.ConfigDir = if ($CustomConfigPath) { $CustomConfigPath } else { Join-Path $env:ProgramData "PyLiRP" }
            $paths.LogDir = Join-Path $env:ProgramData "PyLiRP\logs"
            $paths.DataDir = Join-Path $env:ProgramData "PyLiRP\data"
            $paths.Mode = "System (Admin)"
        }
    }
    
    return $paths
}

function Test-PythonInstallation {
    Write-Host "Checking Python installation..." -ForegroundColor Cyan
    
    try {
        # Test if python command exists
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            Write-Host "Python command not found in PATH" -ForegroundColor Red
            Write-Host "Please install Python 3.8+ from https://www.python.org/downloads/" -ForegroundColor Yellow
            Write-Host "Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
            return $false
        }
        
        Write-Host "Python command found at: $($pythonCmd.Source)" -ForegroundColor Green
        
        # Get Python version
        $pythonVersion = & python --version 2>&1
        Write-Host "Python version output: $pythonVersion" -ForegroundColor Cyan
        
        if ($pythonVersion -match "Python (\d+)\.(\d+)\.?(\d*)") {
            $majorVersion = [int]$matches[1]
            $minorVersion = [int]$matches[2]
            
            Write-Host "Detected Python version: $majorVersion.$minorVersion" -ForegroundColor Cyan
            
            if ($majorVersion -eq 3 -and $minorVersion -ge 8) {
                Write-Host "Python version check passed: $pythonVersion" -ForegroundColor Green
                return $true
            } else {
                Write-Host "Python 3.8+ required, found $pythonVersion" -ForegroundColor Red
                return $false
            }
        } else {
            Write-Host "Could not parse Python version: $pythonVersion" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "Error checking Python: $_" -ForegroundColor Red
        Write-Host "Exception details: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Install-PythonPackages {
    Write-Status "Installing Python packages..."
    
    try {
        # Upgrade pip
        & python -m pip install --upgrade pip --user
        
        # Install base requirements
        if (Test-Path "requirements.txt") {
            & python -m pip install -r requirements.txt --user
        }
        
        # Install Windows-specific packages
        if (Test-Path "requirements_windows.txt") {
            & python -m pip install -r requirements_windows.txt --user
        } else {
            # Install essential Windows packages
            & python -m pip install pywin32 psutil --user
        }
        
        Write-Success "Python packages installed"
        return $true
    } catch {
        Write-Error "Failed to install Python packages: $_"
        return $false
    }
}

function New-InstallationDirectories {
    param($Paths)
    
    Write-Status "Creating directories..."
    
    $directories = @(
        $Paths.InstallDir,
        $Paths.ConfigDir, 
        $Paths.LogDir,
        $Paths.DataDir
    )
    
    foreach ($dir in $directories) {
        try {
            if (!(Test-Path $dir)) {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
                Write-Status "Created directory: $dir"
            } else {
                Write-Status "Directory exists: $dir"
            }
        } catch {
            Write-Error "Failed to create directory ${dir}: $_"
            return $false
        }
    }
    
    Write-Success "Directories created successfully"
    return $true
}

function Copy-ApplicationFiles {
    param($Paths)
    
    Write-Status "Installing application files..."
    
    try {
        # Copy Python modules
        $pyFiles = Get-ChildItem -Path "*.py"
        foreach ($file in $pyFiles) {
            Copy-Item $file.FullName -Destination $Paths.InstallDir -Force
            Write-Status "Copied: $($file.Name)"
        }
        
        # Copy configuration template
        $configSource = if (Test-Path "config.yaml") { "config.yaml" } else { $null }
        $configDest = Join-Path $Paths.ConfigDir "config.yaml"
        
        if ($configSource -and (!(Test-Path $configDest) -or $Force)) {
            Copy-Item $configSource -Destination $configDest -Force
            Write-Status "Copied configuration template"
        }
        
        # Copy requirements files
        $reqFiles = @("requirements.txt", "requirements_windows.txt")
        foreach ($reqFile in $reqFiles) {
            if (Test-Path $reqFile) {
                Copy-Item $reqFile -Destination $Paths.InstallDir -Force
            }
        }
        
        # Create startup script
        $startupScript = @"
@echo off
REM PyLiRP Startup Script
cd /d "$($Paths.InstallDir)"
python main.py --config "$($Paths.ConfigDir)\config.yaml" %*
"@
        
        $startupBat = Join-Path $Paths.InstallDir "start_pyslirp.bat"
        $startupScript | Out-File -FilePath $startupBat -Encoding ASCII
        
        Write-Success "Application files installed"
        return $true
    } catch {
        Write-Error "Failed to copy application files: $_"
        return $false
    }
}

function New-WindowsConfiguration {
    param($Paths)
    
    Write-Status "Creating Windows-specific configuration..."
    
    $configFile = Join-Path $Paths.ConfigDir "config.yaml"
    
    # Only create if doesn't exist or Force is specified
    if (!(Test-Path $configFile) -or $Force) {
        
        $windowsConfig = @"
# PyLiRP Windows Userspace Configuration
# Configured for operation without administrator privileges

serial:
  port: COM1  # Change to your COM port (use --list-com-ports to see available)
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
  # Common Windows services
  22:
    host: 127.0.0.1
    port: 22
    name: SSH
    enabled: false  # Enable if SSH server is running
    
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
    name: Remote Desktop (RDP)
    enabled: true
    max_connections: 5
    
  5900:
    host: 127.0.0.1
    port: 5900
    name: VNC
    enabled: false
    max_connections: 3
    
  8080:
    host: 127.0.0.1
    port: 8080
    name: HTTP Alt
    enabled: true

# Security (no admin privileges required)
security:
  allowed_ports: [22, 80, 443, 3389, 5900, 8080]
  rate_limiting:
    enabled: true
    connections_per_second: 10
    burst_size: 20
  connection_limits:
    global_max_connections: 100
    per_service_max: 20
    per_ip_max: 10

# Logging (user-writable paths)
logging:
  level: INFO
  file:
    enabled: true
    path: $($Paths.LogDir.Replace('\', '/'))/pyslirp.log
    max_size: 10MB
    rotate_count: 5
  console:
    enabled: true
    color: true

# Monitoring (user ports)
monitoring:
  enable_metrics: true
  metrics_port: 9090
  health_check:
    enabled: true
    port: 9091
  packet_capture:
    enabled: false
    pcap_file: $($Paths.DataDir.Replace('\', '/'))/capture.pcap

# Windows-specific settings
windows:
  userspace_mode: true
  startup_method: task  # task, startup, registry, manual
  show_notifications: true
  use_event_log: false  # Disabled for userspace mode
  process_priority: normal
  auto_detect_com_ports: true

# Error recovery
error_recovery:
  auto_reconnect_serial: true
  serial_reconnect_delay: 5
  max_serial_reconnect_attempts: 5
"@
        
        try {
            $windowsConfig | Out-File -FilePath $configFile -Encoding UTF8
            Write-Success "Configuration created: $configFile"
            return $true
        } catch {
            Write-Error "Failed to create configuration: $_"
            return $false
        }
    } else {
        Write-Status "Configuration file already exists: $configFile"
        return $true
    }
}

function Install-UserSpaceService {
    param($Paths, $StartupMethod)
    
    if ($StartupMethod -eq "manual") {
        Write-Status "Manual startup selected - no automatic startup configured"
        return $true
    }
    
    Write-Status "Installing userspace startup using method: $StartupMethod"
    
    $scriptPath = Join-Path $Paths.InstallDir "main.py"
    $configPath = Join-Path $Paths.ConfigDir "config.yaml"
    
    try {
        switch ($StartupMethod) {
            "task" {
                # Use Task Scheduler
                cd $Paths.InstallDir
                $result = & python main.py --install-task --config $configPath --userspace 2>$null
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Scheduled task installed"
                    return $true
                } else {
                    Write-Warning "Task Scheduler installation failed, trying startup folder..."
                    return Install-UserSpaceService -Paths $Paths -StartupMethod "startup"
                }
            }
            "startup" {
                # Use startup folder shortcut
                $startupFolder = [Environment]::GetFolderPath('Startup')
                $shortcutPath = Join-Path $startupFolder "PyLiRP.lnk"
                
                $WshShell = New-Object -ComObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut($shortcutPath)
                $Shortcut.TargetPath = "python.exe"
                $Shortcut.Arguments = "`"$scriptPath`" --config `"$configPath`" --daemon"
                $Shortcut.WorkingDirectory = $Paths.InstallDir
                $Shortcut.Description = "Python SLiRP PPP Bridge"
                $Shortcut.Save()
                
                Write-Success "Added to startup folder"
                return $true
            }
            "registry" {
                # Use registry run key (current user)
                $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
                $command = "`"python.exe`" `"$scriptPath`" --config `"$configPath`" --daemon"
                Set-ItemProperty -Path $regPath -Name "PyLiRP" -Value $command
                
                Write-Success "Added to registry run key"
                return $true
            }
            default {
                Write-Error "Unknown startup method: $StartupMethod"
                return $false
            }
        }
    } catch {
        Write-Error "Failed to install userspace service: $_"
        return $false
    }
}

function Set-UserEnvironmentVariables {
    param($Paths)
    
    Write-Status "Setting user environment variables..."
    
    try {
        # Set user environment variables (no admin required)
        [Environment]::SetEnvironmentVariable("PYSLIRP_INSTALL_PATH", $Paths.InstallDir, "User")
        [Environment]::SetEnvironmentVariable("PYSLIRP_CONFIG_PATH", $Paths.ConfigDir, "User") 
        [Environment]::SetEnvironmentVariable("PYSLIRP_LOG_PATH", $Paths.LogDir, "User")
        [Environment]::SetEnvironmentVariable("PYSLIRP_MODE", $Paths.Mode, "User")
        
        Write-Success "Environment variables set"
        return $true
    } catch {
        Write-Warning "Failed to set environment variables (non-critical): $_"
        return $true  # Non-critical failure
    }
}

function New-DesktopShortcuts {
    param($Paths)
    
    Write-Status "Creating desktop shortcuts..."
    
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $WshShell = New-Object -ComObject WScript.Shell
        
        # Main application shortcut
        $shortcut = $WshShell.CreateShortcut("$desktop\PyLiRP.lnk")
        $shortcut.TargetPath = "python.exe"
        $shortcut.Arguments = "`"$(Join-Path $Paths.InstallDir 'main.py')`" --config `"$(Join-Path $Paths.ConfigDir 'config.yaml')`""
        $shortcut.WorkingDirectory = $Paths.InstallDir
        $shortcut.Description = "Python SLiRP PPP Bridge"
        $shortcut.Save()
        
        # Configuration shortcut
        $shortcut = $WshShell.CreateShortcut("$desktop\PyLiRP Config.lnk")
        $shortcut.TargetPath = "notepad.exe"
        $shortcut.Arguments = "`"$(Join-Path $Paths.ConfigDir 'config.yaml')`""
        $shortcut.Description = "Edit PyLiRP Configuration"
        $shortcut.Save()
        
        Write-Success "Desktop shortcuts created"
        return $true
    } catch {
        Write-Warning "Failed to create desktop shortcuts: $_"
        return $true  # Non-critical failure
    }
}

function Test-ComPortAccess {
    Write-Status "Testing COM port access..."
    
    try {
        # List available COM ports
        $scriptPath = Join-Path $PWD "main.py"
        if (Test-Path $scriptPath) {
            Write-Status "Available COM ports:"
            $ports = & python $scriptPath --list-com-ports 2>$null
            if ($ports) {
                $ports | ForEach-Object { Write-Host "  $_" -ForegroundColor Cyan }
                return $true
            } else {
                Write-Warning "No COM ports detected or access denied"
                return $false
            }
        } else {
            Write-Warning "Cannot test COM ports - main.py not found"
            return $false
        }
    } catch {
        Write-Warning "COM port test failed: $_"
        return $false
    }
}

function Show-PostInstallInfo {
    param($Paths, $StartupMethod)
    
    Write-Success "PyLiRP Windows Userspace installation completed!"
    
    Write-Host ""
    Write-Host "=== Installation Summary ===" -ForegroundColor Yellow
    Write-Host "Mode: $($Paths.Mode)"
    Write-Host "Install Path: $($Paths.InstallDir)"
    Write-Host "Config Path: $($Paths.ConfigDir)"  
    Write-Host "Log Path: $($Paths.LogDir)"
    Write-Host "Startup Method: $StartupMethod"
    Write-Host "Admin Privileges: $(if (Test-AdminPrivileges) { 'Yes' } else { 'No (Userspace Mode)' })"
    
    Write-Host ""
    Write-Host "=== Next Steps ===" -ForegroundColor Yellow
    Write-Host "1. Edit configuration: $($Paths.ConfigDir)\config.yaml"
    Write-Host "2. Set your COM port in the configuration"
    Write-Host "3. Run PyLiRP: python `"$($Paths.InstallDir)\main.py`" --config `"$($Paths.ConfigDir)\config.yaml`""
    Write-Host "4. Or use the desktop shortcut: PyLiRP.lnk"
    
    Write-Host ""
    Write-Host "=== Startup Management ===" -ForegroundColor Yellow
    if ($StartupMethod -eq "task") {
        Write-Host "Task Scheduler: schtasks /query /tn PyLiRP-UserSpace"
        Write-Host "Start task: schtasks /run /tn PyLiRP-UserSpace"
    } elseif ($StartupMethod -eq "startup") {
        Write-Host "Startup folder: $([Environment]::GetFolderPath('Startup'))"
    } elseif ($StartupMethod -eq "registry") {
        Write-Host "Registry: HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
    } else {
        Write-Host "Manual startup: Use desktop shortcut or command line"
    }
    
    Write-Host ""
    Write-Host "=== Monitoring ===" -ForegroundColor Yellow
    Write-Host "Metrics: http://localhost:9090/metrics"
    Write-Host "Health: http://localhost:9091/health"
    Write-Host "Logs: $($Paths.LogDir)\pyslirp.log"
    
    Write-Host ""
    Write-Host "=== Commands ===" -ForegroundColor Yellow
    Write-Host "List COM ports: python main.py --list-com-ports"
    Write-Host "Test COM port: python main.py --test-serial COM1"
    Write-Host "Run in console: python main.py --config config.yaml --debug"
    Write-Host "Validate config: python main.py --validate-config config.yaml"
}

# Main installation function
function Install-PyLiRPUserspace {
    Write-Host "PyLiRP Windows Userspace Installation" -ForegroundColor Green
    Write-Host "====================================" -ForegroundColor Green
    Write-Host ""
    
    Write-Status "Starting installation process..."
    
    # Check Python
    Write-Status "Step 1: Checking Python installation..."
    if (-not (Test-PythonInstallation)) {
        Write-Error "Python installation check failed"
        return $false
    }
    Write-Success "Python check passed"
    
    # Get installation paths
    Write-Status "Step 2: Determining installation paths..."
    try {
        $paths = Get-InstallationPaths -Mode $InstallMode -CustomInstallPath $InstallPath -CustomConfigPath $ConfigPath
        
        Write-Status "Installation mode: $($paths.Mode)"
        Write-Status "Install directory: $($paths.InstallDir)"
        Write-Status "Config directory: $($paths.ConfigDir)"
        Write-Status "Log directory: $($paths.LogDir)"
        Write-Status "Data directory: $($paths.DataDir)"
    } catch {
        Write-Error "Failed to determine installation paths: $_"
        return $false
    }
    
    # Installation steps with individual error handling
    Write-Status "Step 3: Creating directories..."
    if (-not (New-InstallationDirectories -Paths $paths)) {
        Write-Error "Failed to create directories"
        return $false
    }
    
    Write-Status "Step 4: Installing Python packages..."
    if (-not (Install-PythonPackages)) {
        Write-Error "Failed to install Python packages"
        return $false
    }
    
    Write-Status "Step 5: Copying application files..."
    if (-not (Copy-ApplicationFiles -Paths $paths)) {
        Write-Error "Failed to copy application files"
        return $false
    }
    
    Write-Status "Step 6: Creating Windows configuration..."
    if (-not (New-WindowsConfiguration -Paths $paths)) {
        Write-Error "Failed to create configuration"
        return $false
    }
    
    Write-Status "Step 7: Setting environment variables..."
    if (-not (Set-UserEnvironmentVariables -Paths $paths)) {
        Write-Warning "Failed to set environment variables (non-critical)"
    }
    
    Write-Status "Step 8: Creating desktop shortcuts..."
    if (-not (New-DesktopShortcuts -Paths $paths)) {
        Write-Warning "Failed to create desktop shortcuts (non-critical)"
    }
    
    # Add startup installation if not manual
    if (-not $NoAutoStart -and $StartupMethod -ne "manual") {
        Write-Status "Step 9: Installing startup method ($StartupMethod)..."
        if (-not (Install-UserSpaceService -Paths $paths -StartupMethod $StartupMethod)) {
            Write-Warning "Failed to install startup service (non-critical)"
        }
    } else {
        Write-Status "Step 9: Skipping startup installation (manual mode)"
    }
    
    # Test COM port access
    Test-ComPortAccess
    
    # Show completion info
    Show-PostInstallInfo -Paths $paths -StartupMethod $StartupMethod
    
    return $true
}

# Main entry point - always execute when script is run
Write-Host "Starting PyLiRP installation..." -ForegroundColor Green
Write-Host "Current parameters:" -ForegroundColor Yellow
Write-Host "  InstallMode: $InstallMode" -ForegroundColor Cyan
Write-Host "  InstallPath: $InstallPath" -ForegroundColor Cyan  
Write-Host "  ConfigPath: $ConfigPath" -ForegroundColor Cyan
Write-Host "  StartupMethod: $StartupMethod" -ForegroundColor Cyan
Write-Host ""

try {
    $success = Install-PyLiRPUserspace
    if ($success) {
        Write-Host ""
        Write-Success "Installation completed successfully!"
        
        # Offer to start immediately
        $startNow = Read-Host "Start PyLiRP now? (y/N)"
        if ($startNow -eq 'y' -or $startNow -eq 'Y') {
            Write-Status "Starting PyLiRP..."
            $paths = Get-InstallationPaths -Mode $InstallMode -CustomInstallPath $InstallPath -CustomConfigPath $ConfigPath
            Set-Location $paths.InstallDir
            & python main.py --config "$($paths.ConfigDir)\config.yaml" --debug
        }
    } else {
        Write-Error "Installation failed"
        Read-Host "Press Enter to exit"
        exit 1
    }
} catch {
    Write-Error "Installation error: $_"
    Write-Host "Stack trace:" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}