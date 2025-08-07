# Simple test script to debug installation issues
[CmdletBinding()]
param()

Write-Host "PyLiRP Installation Test Script" -ForegroundColor Green
Write-Host "===============================" -ForegroundColor Green
Write-Host ""

# Test basic PowerShell functionality
Write-Host "PowerShell Version: $($PSVersionTable.PSVersion)" -ForegroundColor Cyan
Write-Host "Execution Policy: $(Get-ExecutionPolicy)" -ForegroundColor Cyan
Write-Host "Current Directory: $(Get-Location)" -ForegroundColor Cyan
Write-Host "Current User: $env:USERNAME" -ForegroundColor Cyan
Write-Host ""

# Test Python installation
Write-Host "Testing Python..." -ForegroundColor Yellow
try {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        Write-Host "✓ Python found at: $($pythonCmd.Source)" -ForegroundColor Green
        $pythonVersion = & python --version 2>&1
        Write-Host "✓ Python version: $pythonVersion" -ForegroundColor Green
        
        # Test pip
        $pipVersion = & python -m pip --version 2>&1
        Write-Host "✓ Pip version: $pipVersion" -ForegroundColor Green
    } else {
        Write-Host "✗ Python not found in PATH" -ForegroundColor Red
    }
} catch {
    Write-Host "✗ Error testing Python: $_" -ForegroundColor Red
}

Write-Host ""

# Test directory permissions
Write-Host "Testing directory permissions..." -ForegroundColor Yellow

$testDirs = @{
    "User Profile" = $env:USERPROFILE
    "AppData Roaming" = $env:APPDATA  
    "AppData Local" = $env:LOCALAPPDATA
    "Temp" = $env:TEMP
    "Current Directory" = (Get-Location).Path
}

foreach ($name in $testDirs.Keys) {
    $path = $testDirs[$name]
    try {
        $testFile = Join-Path $path "pyslirp_test.tmp"
        "test" | Out-File -FilePath $testFile -Force
        Remove-Item $testFile -Force
        Write-Host "✓ $name ($path)" -ForegroundColor Green
    } catch {
        Write-Host "✗ $name ($path) - $_" -ForegroundColor Red
    }
}

Write-Host ""

# Test file presence
Write-Host "Testing required files..." -ForegroundColor Yellow

$requiredFiles = @(
    "install_windows_userspace.ps1",
    "main.py",
    "config.yaml"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "✓ $file found" -ForegroundColor Green
    } else {
        Write-Host "✗ $file missing" -ForegroundColor Red
    }
}

Write-Host ""

# Test admin privileges
Write-Host "Testing privileges..." -ForegroundColor Yellow
try {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        Write-Host "✓ Running with Administrator privileges" -ForegroundColor Green
    } else {
        Write-Host "ℹ Running with User privileges (userspace mode will be used)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Error checking privileges: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Test completed. Press Enter to exit..." -ForegroundColor Cyan
Read-Host