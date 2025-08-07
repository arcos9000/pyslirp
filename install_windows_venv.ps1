# PyLiRP Windows Installation Script with Virtual Environment Support
# PowerShell script for installing Python SLiRP with proper venv handling

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
    [switch]$Force = $false,
    
    [Parameter(Mandatory=$false)]
    [string]$PythonVersion = "3.8"  # Minimum Python version
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
            $paths.VenvDir = Join-Path $baseDir ".venv"
            $paths.Mode = "Portable"
        }
        "user" {
            $homeDir = $env:USERPROFILE
            $appData = $env:APPDATA
            
            $paths.InstallDir = if ($CustomInstallPath) { $CustomInstallPath } else { Join-Path $homeDir "PyLiRP" }
            $paths.ConfigDir = if ($CustomConfigPath) { $CustomConfigPath } else { Join-Path $appData "PyLiRP" }
            $paths.LogDir = Join-Path $appData "PyLiRP\logs"
            $paths.DataDir = Join-Path $appData "PyLiRP\data"
            $paths.VenvDir = Join-Path $paths.InstallDir ".venv"
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
            $paths.VenvDir = Join-Path $paths.InstallDir ".venv"
            $paths.Mode = "System (Admin)"
        }
    }
    
    return $paths
}

function Test-PythonVersion {
    param([string]$PythonExe, [string]$MinVersion)
    
    try {
        $versionOutput = & $PythonExe --version 2>&1
        if ($versionOutput -match "Python (\d+)\.(\d+)\.?(\d*)") {
            $majorVersion = [int]$matches[1]
            $minorVersion = [int]$matches[2]
            $patchVersion = if ($matches[3]) { [int]$matches[3] } else { 0 }
            
            $currentVersion = "$majorVersion.$minorVersion"
            $minVersionParts = $MinVersion.Split('.')
            $minMajor = [int]$minVersionParts[0]
            $minMinor = [int]$minVersionParts[1]
            
            if ($majorVersion -gt $minMajor -or ($majorVersion -eq $minMajor -and $minorVersion -ge $minMinor)) {
                return @{
                    Valid = $true
                    Version = "$majorVersion.$minorVersion.$patchVersion"
                    Executable = $PythonExe
                }
            } else {
                return @{
                    Valid = $false
                    Version = "$majorVersion.$minorVersion.$patchVersion"
                    Executable = $PythonExe
                    Reason = "Version too old (need $MinVersion+)"
                }
            }
        } else {
            return @{
                Valid = $false
                Version = "unknown"
                Executable = $PythonExe
                Reason = "Could not parse version: $versionOutput"
            }
        }
    } catch {
        return @{
            Valid = $false
            Version = "unknown"
            Executable = $PythonExe
            Reason = "Failed to execute: $_"
        }
    }
}

function Find-SuitablePython {
    param([string]$MinVersion = "3.8")
    
    Write-Status "Searching for suitable Python installation..."
    
    # List of Python executables to try
    $pythonCandidates = @(
        "python",
        "python3",
        "python3.12",
        "python3.11", 
        "python3.10",
        "python3.9",
        "python3.8"
    )
    
    # Also check Python Launcher
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $pythonCandidates = @("py -3") + $pythonCandidates
    }
    
    foreach ($pythonCmd in $pythonCandidates) {
        try {
            $pythonExe = $null
            if ($pythonCmd -eq "py -3") {
                # Special handling for Python Launcher
                $pythonExe = "py"
                $result = Test-PythonVersion -PythonExe "py" -MinVersion $MinVersion
                if ($result.Valid) {
                    Write-Success "Found suitable Python via launcher: py (version $($result.Version))"
                    return @{
                        Executable = "py"
                        Arguments = @("-3")
                        Version = $result.Version
                    }
                }
            } else {
                $pythonExe = Get-Command $pythonCmd -ErrorAction SilentlyContinue
                if ($pythonExe) {
                    $result = Test-PythonVersion -PythonExe $pythonExe.Source -MinVersion $MinVersion
                    if ($result.Valid) {
                        Write-Success "Found suitable Python: $($pythonExe.Source) (version $($result.Version))"
                        return @{
                            Executable = $pythonExe.Source
                            Arguments = @()
                            Version = $result.Version
                        }
                    } else {
                        Write-Warning "$($pythonExe.Source): $($result.Reason)"
                    }
                }
            }
        } catch {
            Write-Warning "Error testing $pythonCmd: $_"
        }
    }
    
    return $null
}

function Test-ScoopInstalled {
    try {
        $scoopCmd = Get-Command scoop -ErrorAction SilentlyContinue
        if ($scoopCmd) {
            Write-Status "Scoop package manager found at: $($scoopCmd.Source)"
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

function Install-Scoop {
    Write-Status "Installing Scoop package manager..."
    
    try {
        # Check if execution policy allows installation
        $policy = Get-ExecutionPolicy
        if ($policy -eq "Restricted") {
            Write-Warning "Execution policy is Restricted, temporarily allowing for Scoop installation"
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
        }
        
        # Install Scoop
        $installScript = Invoke-RestMethod -Uri "https://get.scoop.sh"
        Invoke-Expression $installScript
        
        # Refresh PATH
        $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
        
        # Verify installation
        if (Test-ScoopInstalled) {
            Write-Success "Scoop installed successfully"
            return $true
        } else {
            Write-Error "Scoop installation verification failed"
            return $false
        }
        
    } catch {
        Write-Error "Failed to install Scoop: $_"
        Write-Status "You can install Scoop manually by running:"
        Write-Host "irm get.scoop.sh | iex" -ForegroundColor Cyan
        return $false
    }
}

function Install-PythonWithScoop {
    param([string]$MinVersion = "3.8")
    
    Write-Status "Installing Python via Scoop package manager..."
    
    try {
        # Ensure Scoop is installed
        if (-not (Test-ScoopInstalled)) {
            Write-Status "Scoop not found, installing..."
            if (-not (Install-Scoop)) {
                return $null
            }
        }
        
        # Add Scoop buckets for more Python versions
        Write-Status "Adding Scoop buckets..."
        & scoop bucket add versions 2>$null || Write-Warning "Versions bucket already added or failed"
        & scoop bucket add main 2>$null || Write-Warning "Main bucket already added or failed"
        
        # Install Python (Scoop installs latest stable by default)
        Write-Status "Installing Python via Scoop..."
        & scoop install python
        
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Standard Python installation failed, trying Python 3.11..."
            & scoop install python311
        }
        
        # Refresh PATH to include Scoop Python
        $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
        
        # Give it a moment and try to find Python
        Start-Sleep -Seconds 2
        return Find-SuitablePython -MinVersion $MinVersion
        
    } catch {
        Write-Error "Failed to install Python via Scoop: $_"
        return $null
    }
}

function Install-PythonFromWeb {
    param([string]$MinVersion = "3.8")
    
    Write-Warning "Fallback: Installing Python from official installer..."
    
    # Determine the latest Python version to install
    $pythonVersionToInstall = "3.11.7"  # Stable version
    $downloadUrl = "https://www.python.org/ftp/python/$pythonVersionToInstall/python-$pythonVersionToInstall-amd64.exe"
    
    Write-Status "Downloading Python $pythonVersionToInstall..."
    $tempFile = Join-Path $env:TEMP "python-installer.exe"
    
    try {
        # Download Python installer
        Write-Status "Downloading from: $downloadUrl"
        $webClient = New-Object System.Net.WebClient
        $webClient.DownloadFile($downloadUrl, $tempFile)
        
        Write-Status "Installing Python $pythonVersionToInstall..."
        
        # Install Python silently
        $installArgs = @(
            "/quiet",
            "InstallAllUsers=0",  # Install for current user only
            "PrependPath=1",      # Add to PATH
            "Include_test=0"      # Don't install test suite
        )
        
        $process = Start-Process -FilePath $tempFile -ArgumentList $installArgs -Wait -PassThru
        
        if ($process.ExitCode -eq 0) {
            Write-Success "Python installed successfully"
            
            # Refresh PATH
            $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
            
            # Give it a moment and try to find Python again
            Start-Sleep -Seconds 3
            return Find-SuitablePython -MinVersion $MinVersion
        } else {
            Write-Error "Python installation failed with exit code: $($process.ExitCode)"
            return $null
        }
        
    } catch {
        Write-Error "Failed to download or install Python: $_"
        return $null
    } finally {
        if (Test-Path $tempFile) {
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        }
    }
}

function New-VirtualEnvironment {
    param($Paths, $PythonInfo)
    
    Write-Status "Creating virtual environment..."
    Write-Status "Virtual environment path: $($Paths.VenvDir)"
    
    # Remove existing venv if it's broken or if Force is specified
    if (Test-Path $Paths.VenvDir) {
        $venvPython = Join-Path $Paths.VenvDir "Scripts\python.exe"
        if ($Force -or -not (Test-Path $venvPython)) {
            Write-Warning "Removing existing virtual environment..."
            Remove-Item $Paths.VenvDir -Recurse -Force
        } else {
            # Test if existing venv works
            try {
                & $venvPython -c "import sys; print('Existing venv OK')" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Using existing virtual environment"
                    return $true
                } else {
                    Write-Warning "Existing virtual environment is broken, recreating..."
                    Remove-Item $Paths.VenvDir -Recurse -Force
                }
            } catch {
                Write-Warning "Cannot test existing venv, recreating..."
                Remove-Item $Paths.VenvDir -Recurse -Force
            }
        }
    }
    
    # Create new virtual environment
    Write-Status "Creating new virtual environment with Python $($PythonInfo.Version)..."
    
    try {
        $createArgs = $PythonInfo.Arguments + @("-m", "venv", $Paths.VenvDir)
        & $PythonInfo.Executable @createArgs
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create virtual environment (exit code: $LASTEXITCODE)"
            return $false
        }
        
        # Verify virtual environment
        $venvPython = Join-Path $Paths.VenvDir "Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Write-Error "Virtual environment creation failed - python.exe not found"
            return $false
        }
        
        # Test virtual environment
        & $venvPython -c "import sys; print(f'Virtual environment created with Python {sys.version}')"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Virtual environment python is not working"
            return $false
        }
        
        Write-Success "Virtual environment created successfully"
        return $true
        
    } catch {
        Write-Error "Failed to create virtual environment: $_"
        return $false
    }
}

function Install-PythonPackages {
    param($Paths)
    
    Write-Status "Installing Python packages in virtual environment..."
    
    $venvPython = Join-Path $Paths.VenvDir "Scripts\python.exe"
    $venvPip = Join-Path $Paths.VenvDir "Scripts\pip.exe"
    
    if (-not (Test-Path $venvPython)) {
        Write-Error "Virtual environment Python not found: $venvPython"
        return $false
    }
    
    try {
        # Upgrade pip in virtual environment
        Write-Status "Upgrading pip in virtual environment..."
        & $venvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to upgrade pip in virtual environment"
            return $false
        }
        
        # Install base requirements
        if (Test-Path "requirements.txt") {
            Write-Status "Installing base requirements..."
            & $venvPip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Failed to install base requirements"
                return $false
            }
        } else {
            Write-Warning "requirements.txt not found, installing minimal dependencies"
            & $venvPip install pyserial pyserial-asyncio pyyaml
        }
        
        # Install Windows-specific packages
        if (Test-Path "requirements_windows.txt") {
            Write-Status "Installing Windows-specific requirements..."
            & $venvPip install -r requirements_windows.txt
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Some Windows-specific packages failed to install"
            }
        } else {
            Write-Status "Installing essential Windows packages..."
            & $venvPip install pywin32 psutil
        }
        
        Write-Success "Python packages installed successfully"
        
        # Verify key packages
        Write-Status "Verifying package installation..."
        $packages = @("serial", "serial_asyncio", "yaml")
        foreach ($package in $packages) {
            & $venvPython -c "import $package; print('✓ $package')" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ $package" -ForegroundColor Green
            } else {
                Write-Host "✗ $package failed to import" -ForegroundColor Red
                return $false
            }
        }
        
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
        
        Write-Success "Application files installed"
        return $true
    } catch {
        Write-Error "Failed to copy application files: $_"
        return $false
    }
}

function New-StartupScripts {
    param($Paths)
    
    Write-Status "Creating startup scripts..."
    
    $venvPython = Join-Path $Paths.VenvDir "Scripts\python.exe"
    $mainScript = Join-Path $Paths.InstallDir "main.py"
    $configFile = Join-Path $Paths.ConfigDir "config.yaml"
    
    # Create batch file startup script
    $startupScript = @"
@echo off
REM PyLiRP Startup Script with Virtual Environment
cd /d "$($Paths.InstallDir)"
"$venvPython" "$mainScript" --config "$configFile" %*
"@
    
    $startupBat = Join-Path $Paths.InstallDir "start_pyslirp.bat"
    $startupScript | Out-File -FilePath $startupBat -Encoding ASCII
    
    # Create PowerShell startup script
    $psScript = @"
# PyLiRP PowerShell Startup Script
Set-Location "$($Paths.InstallDir)"
& "$venvPython" "$mainScript" --config "$configFile" @args
"@
    
    $startupPs1 = Join-Path $Paths.InstallDir "start_pyslirp.ps1"
    $psScript | Out-File -FilePath $startupPs1 -Encoding UTF8
    
    Write-Success "Startup scripts created"
    return $true
}

function Install-UserSpaceService {
    param($Paths, $StartupMethod)
    
    if ($StartupMethod -eq "manual") {
        Write-Status "Manual startup selected - no automatic startup configured"
        return $true
    }
    
    Write-Status "Installing userspace startup using method: $StartupMethod"
    
    $venvPython = Join-Path $Paths.VenvDir "Scripts\python.exe"
    $scriptPath = Join-Path $Paths.InstallDir "main.py"
    $configPath = Join-Path $Paths.ConfigDir "config.yaml"
    
    try {
        switch ($StartupMethod) {
            "task" {
                # Use Task Scheduler with virtual environment
                Write-Status "Creating scheduled task with virtual environment support..."
                
                $taskName = "PyLiRP-UserSpace"
                $taskCommand = "`"$venvPython`" `"$scriptPath`" --config `"$configPath`" --daemon"
                
                # Create task using schtasks
                $schtasksArgs = @(
                    "/create",
                    "/tn", $taskName,
                    "/tr", $taskCommand,
                    "/sc", "onstart",
                    "/ru", $env:USERNAME,
                    "/f"
                )
                
                $result = schtasks @schtasksArgs
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Scheduled task created successfully"
                    Write-Status "Task name: $taskName"
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
                $Shortcut.TargetPath = $venvPython
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
                $command = "`"$venvPython`" `"$scriptPath`" --config `"$configPath`" --daemon"
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

function Show-PostInstallInfo {
    param($Paths, $StartupMethod)
    
    Write-Success "PyLiRP Windows installation with virtual environment completed!"
    
    $venvPython = Join-Path $Paths.VenvDir "Scripts\python.exe"
    $venvVersion = & $venvPython --version 2>$null
    
    Write-Host ""
    Write-Host "=== Installation Summary ===" -ForegroundColor Yellow
    Write-Host "Mode: $($Paths.Mode)"
    Write-Host "Install Path: $($Paths.InstallDir)"
    Write-Host "Config Path: $($Paths.ConfigDir)"  
    Write-Host "Log Path: $($Paths.LogDir)"
    Write-Host "Virtual Environment: $($Paths.VenvDir)"
    Write-Host "Python Version: $venvVersion"
    Write-Host "Startup Method: $StartupMethod"
    Write-Host "Admin Privileges: $(if (Test-AdminPrivileges) { 'Yes' } else { 'No (Userspace Mode)' })"
    
    Write-Host ""
    Write-Host "=== Next Steps ===" -ForegroundColor Yellow
    Write-Host "1. Edit configuration: $($Paths.ConfigDir)\config.yaml"
    Write-Host "2. Set your COM port in the configuration"
    Write-Host "3. Run PyLiRP: $venvPython `"$($Paths.InstallDir)\main.py`" --config `"$($Paths.ConfigDir)\config.yaml`""
    Write-Host "4. Or use the batch file: $($Paths.InstallDir)\start_pyslirp.bat"
    
    Write-Host ""
    Write-Host "=== Virtual Environment ===" -ForegroundColor Yellow
    Write-Host "Python Executable: $venvPython"
    Write-Host "Pip Executable: $(Join-Path $Paths.VenvDir 'Scripts\pip.exe')"
    Write-Host "Add packages: $(Join-Path $Paths.VenvDir 'Scripts\pip.exe') install <package>"
    Write-Host "List packages: $(Join-Path $Paths.VenvDir 'Scripts\pip.exe') list"
    
    Write-Host ""
    Write-Host "=== Commands ===" -ForegroundColor Yellow
    Write-Host "List COM ports: $venvPython main.py --list-com-ports"
    Write-Host "Test COM port: $venvPython main.py --test-serial COM1"
    Write-Host "Run in console: $venvPython main.py --config config.yaml --debug"
    Write-Host "Validate config: $venvPython main.py --validate-config config.yaml"
}

# Main installation function
function Install-PyLiRPUserspace {
    Write-Host "PyLiRP Windows Installation with Virtual Environment Support" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host ""
    
    # Step 1: Find or install suitable Python
    Write-Status "Step 1: Finding suitable Python installation..."
    $pythonInfo = Find-SuitablePython -MinVersion $PythonVersion
    
    if (-not $pythonInfo) {
        Write-Warning "No suitable Python found, attempting automatic installation..."
        
        # Try Scoop first (preferred method)
        Write-Status "Attempting installation via Scoop package manager..."
        $pythonInfo = Install-PythonWithScoop -MinVersion $PythonVersion
        
        # If Scoop fails, fall back to web installer
        if (-not $pythonInfo) {
            Write-Warning "Scoop installation failed, trying official installer..."
            $pythonInfo = Install-PythonFromWeb -MinVersion $PythonVersion
        }
        
        if (-not $pythonInfo) {
            Write-Error "Failed to find or install suitable Python"
            Write-Host ""
            Write-Host "=== Manual Installation Options ===" -ForegroundColor Yellow
            Write-Host "1. Official Python installer: https://www.python.org/downloads/" -ForegroundColor Cyan
            Write-Host "   - Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Cyan
            Write-Host "2. Scoop package manager (recommended): https://scoop.sh/" -ForegroundColor Cyan
            Write-Host "   - Run: irm get.scoop.sh | iex" -ForegroundColor Cyan
            Write-Host "   - Then: scoop install python" -ForegroundColor Cyan
            Write-Host "3. Microsoft Store: Search for 'Python 3.11'" -ForegroundColor Cyan
            return $false
        }
    }
    
    Write-Success "Using Python: $($pythonInfo.Executable) (version $($pythonInfo.Version))"
    
    # Step 2: Get installation paths
    Write-Status "Step 2: Determining installation paths..."
    try {
        $paths = Get-InstallationPaths -Mode $InstallMode -CustomInstallPath $InstallPath -CustomConfigPath $ConfigPath
        
        Write-Status "Installation mode: $($paths.Mode)"
        Write-Status "Install directory: $($paths.InstallDir)"
        Write-Status "Virtual environment: $($paths.VenvDir)"
        Write-Status "Config directory: $($paths.ConfigDir)"
    } catch {
        Write-Error "Failed to determine installation paths: $_"
        return $false
    }
    
    # Step 3: Create directories
    Write-Status "Step 3: Creating directories..."
    if (-not (New-InstallationDirectories -Paths $paths)) {
        Write-Error "Failed to create directories"
        return $false
    }
    
    # Step 4: Create virtual environment
    Write-Status "Step 4: Creating virtual environment..."
    if (-not (New-VirtualEnvironment -Paths $paths -PythonInfo $pythonInfo)) {
        Write-Error "Failed to create virtual environment"
        return $false
    }
    
    # Step 5: Install Python packages in virtual environment
    Write-Status "Step 5: Installing Python packages in virtual environment..."
    if (-not (Install-PythonPackages -Paths $paths)) {
        Write-Error "Failed to install Python packages"
        return $false
    }
    
    # Step 6: Copy application files
    Write-Status "Step 6: Copying application files..."
    if (-not (Copy-ApplicationFiles -Paths $paths)) {
        Write-Error "Failed to copy application files"
        return $false
    }
    
    # Step 7: Create startup scripts
    Write-Status "Step 7: Creating startup scripts..."
    if (-not (New-StartupScripts -Paths $paths)) {
        Write-Warning "Failed to create startup scripts (non-critical)"
    }
    
    # Step 8: Install startup service if requested
    if (-not $NoAutoStart -and $StartupMethod -ne "manual") {
        Write-Status "Step 8: Installing startup service ($StartupMethod)..."
        if (-not (Install-UserSpaceService -Paths $paths -StartupMethod $StartupMethod)) {
            Write-Warning "Failed to install startup service (non-critical)"
        }
    } else {
        Write-Status "Step 8: Skipping startup installation (manual mode)"
    }
    
    # Show completion info
    Show-PostInstallInfo -Paths $paths -StartupMethod $StartupMethod
    
    return $true
}

# Main entry point
Write-Host "Starting PyLiRP installation with virtual environment support..." -ForegroundColor Green
Write-Host "Current parameters:" -ForegroundColor Yellow
Write-Host "  InstallMode: $InstallMode" -ForegroundColor Cyan
Write-Host "  PythonVersion: $PythonVersion+" -ForegroundColor Cyan
Write-Host "  InstallPath: $InstallPath" -ForegroundColor Cyan  
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
            $venvPython = Join-Path $paths.VenvDir "Scripts\python.exe"
            Set-Location $paths.InstallDir
            & $venvPython "main.py" --config "$($paths.ConfigDir)\config.yaml" --debug
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