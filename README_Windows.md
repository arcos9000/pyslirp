# PyLiRP Windows Installation Guide

Complete guide for installing and running PyLiRP on Windows systems.

## 🔧 Prerequisites

### Python 3.8+
Download and install Python from [python.org](https://www.python.org/downloads/):
- ✅ Add Python to PATH
- ✅ Install pip
- ✅ Install for all users (recommended)

### Administrator Privileges
Required for:
- Installing Windows services
- Configuring firewall rules
- Accessing COM ports (initially)

## 🚀 Quick Installation

### Option 1: Automated PowerShell Installation (Recommended)

1. **Open PowerShell as Administrator**
2. **Allow execution of PowerShell scripts:**
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

3. **Run the installation script:**
   ```powershell
   .\install_windows.ps1
   ```

4. **Follow the prompts**

### Option 2: Manual Installation

1. **Install Python dependencies:**
   ```powershell
   pip install -r requirements_windows.txt
   ```

2. **Copy files to Program Files:**
   ```powershell
   # Create directories
   mkdir "C:\Program Files\PyLiRP"
   mkdir "C:\ProgramData\PyLiRP"
   mkdir "C:\ProgramData\PyLiRP\logs"
   
   # Copy files
   copy *.py "C:\Program Files\PyLiRP\"
   copy config.yaml "C:\ProgramData\PyLiRP\"
   ```

3. **Install as Windows Service:**
   ```powershell
   cd "C:\Program Files\PyLiRP"
   python main.py --install-service --config "C:\ProgramData\PyLiRP\config.yaml"
   ```

## 📝 Configuration

### 1. Edit Configuration File
Edit `C:\ProgramData\PyLiRP\config.yaml`:

```yaml
serial:
  port: COM7          # Change to your COM port
  baudrate: 115200
  flow_control: hardware

services:
  3389:               # Remote Desktop
    host: 127.0.0.1
    port: 3389
    name: Remote Desktop
    enabled: true
    
  80:                 # HTTP
    host: 127.0.0.1
    port: 80
    name: HTTP
    enabled: true
    
  443:                # HTTPS  
    host: 127.0.0.1
    port: 443
    name: HTTPS
    enabled: true
    
  22:                 # SSH (if running SSH server)
    host: 127.0.0.1
    port: 22
    name: SSH
    enabled: false    # Enable if you have SSH server

logging:
  file:
    path: C:/ProgramData/PyLiRP/logs/pyslirp.log
  
# Windows-specific settings
windows:
  use_event_log: true
  show_notifications: true
  process_priority: high
```

### 2. Find Available COM Ports

```powershell
# List COM ports
python main.py --list-com-ports

# Or use Windows Device Manager:
# Device Manager → Ports (COM & LPT)
```

### 3. Test COM Port
```powershell
python main.py --test-serial COM7
```

## 🎮 Service Management

### Service Commands
```powershell
# Start service
sc start PyLiRP
net start PyLiRP

# Stop service  
sc stop PyLiRP
net stop PyLiRP

# Check status
sc query PyLiRP

# View service configuration
sc qc PyLiRP
```

### Service Logs
```powershell
# View application logs
Get-Content "C:\ProgramData\PyLiRP\logs\pyslirp.log" -Tail 50

# View Windows Event Log
Get-EventLog -LogName Application -Source PyLiRP -Newest 20
```

### Automatic Startup
The service is configured to start automatically with Windows. To change this:

```powershell
# Set to manual startup
sc config PyLiRP start=demand

# Set to automatic startup  
sc config PyLiRP start=auto
```

## 🔒 Windows Security

### Firewall Configuration
The installer automatically creates firewall rules:
- **Port 9090**: Metrics endpoint
- **Port 9091**: Health check endpoint

To manually configure:
```powershell
# Add firewall rules
New-NetFirewallRule -DisplayName "PyLiRP-Metrics" -Direction Inbound -Protocol TCP -LocalPort 9090 -Action Allow
New-NetFirewallRule -DisplayName "PyLiRP-Health" -Direction Inbound -Protocol TCP -LocalPort 9091 -Action Allow

# Remove firewall rules
Remove-NetFirewallRule -DisplayName "PyLiRP-Metrics"
Remove-NetFirewallRule -DisplayName "PyLiRP-Health"
```

### COM Port Permissions
By default, COM ports require administrator privileges. To allow standard users:

1. **Device Manager** → **Ports (COM & LPT)**
2. **Right-click your COM port** → **Properties**
3. **Security tab** → **Edit**
4. **Add your user account** with **Full Control**

### Windows Defender
Add PyLiRP to Windows Defender exclusions if needed:
```powershell
Add-MpPreference -ExclusionPath "C:\Program Files\PyLiRP"
Add-MpPreference -ExclusionProcess "python.exe"
```

## 📊 Monitoring on Windows

### Performance Monitor Integration
```powershell
# View performance counters
Get-Counter "\Process(python)\% Processor Time"
Get-Counter "\Process(python)\Working Set"
```

### Event Viewer
1. **Windows + R** → `eventvwr`
2. **Windows Logs** → **Application**
3. **Filter** by source: **PyLiRP**

### Task Manager
Monitor PyLiRP process:
1. **Ctrl+Shift+Esc** → **Task Manager**
2. **Details tab** → Find **python.exe** processes
3. **Services tab** → Find **PyLiRP** service

### Web Interfaces
- **Metrics**: http://localhost:9090/metrics
- **Health**: http://localhost:9091/health  
- **Status**: http://localhost:9090/status

## 🐛 Windows Troubleshooting

### Common Issues

**"Access Denied" on COM port**
```powershell
# Check COM port permissions
icacls \\.\COM7

# Grant permissions (as administrator)
icacls \\.\COM7 /grant Users:F
```

**Service won't start**
```powershell
# Check service status
sc query PyLiRP

# Check dependencies
sc enumdepend PyLiRP

# Check event log
Get-EventLog -LogName Application -Source PyLiRP -Newest 10
```

**Python path issues**
```powershell
# Verify Python installation
python --version
where python

# Check if pip works
pip --version
```

**Port already in use**
```powershell
# Check what's using a port
netstat -ano | findstr :9090

# Kill process if needed (find PID from netstat)
taskkill /PID 1234 /F
```

### Debug Mode

**Run in console for debugging:**
```powershell
cd "C:\Program Files\PyLiRP"
python main.py --config "C:\ProgramData\PyLiRP\config.yaml" --debug
```

**Enable verbose logging:**
```yaml
# In config.yaml
logging:
  level: DEBUG
  console:
    enabled: true
```

### Performance Issues

**High CPU usage:**
1. Lower process priority:
   ```powershell
   # Set normal priority
   wmic process where name="python.exe" CALL setpriority "normal"
   ```

2. Check for loops in logs
3. Reduce logging verbosity

**Memory issues:**
1. Monitor memory usage in Task Manager
2. Check for memory leaks in logs
3. Restart service periodically if needed

## 🔧 Advanced Windows Configuration

### Running Multiple Instances
```powershell
# Create separate service for second instance
sc create PyLiRP2 binPath="python \"C:\Program Files\PyLiRP\main.py\" --config \"C:\ProgramData\PyLiRP\config2.yaml\" --service"
```

### Custom Installation Paths
```powershell
# Install to custom location
.\install_windows.ps1 -InstallPath "D:\MyApps\PyLiRP" -ConfigPath "D:\MyApps\PyLiRP\config"
```

### Network Interface Binding
For systems with multiple network interfaces, configure Windows routing:
```powershell
# View routing table
route print

# Add specific routes if needed
route add 10.0.0.0 MASK 255.255.255.0 10.0.0.1 METRIC 1
```

## 📋 Windows-Specific Features

### Toast Notifications
PyLiRP can show Windows 10/11 toast notifications for important events.

### Windows Event Log Integration
All PyLiRP events are logged to Windows Event Log for enterprise monitoring.

### Performance Counters
System performance integration with Windows Performance Toolkit.

### COM Port Auto-Detection
Automatic detection and enumeration of available COM ports.

### Service Recovery
Windows Service Control Manager handles automatic restart on failures.

## 🔄 Updates and Maintenance

### Updating PyLiRP
```powershell
# Stop service
sc stop PyLiRP

# Update files (backup config first)
copy "C:\ProgramData\PyLiRP\config.yaml" "C:\ProgramData\PyLiRP\config.yaml.backup"

# Install new version (preserves config)
.\install_windows.ps1 -Force

# Start service
sc start PyLiRP
```

### Backup Configuration
```powershell
# Backup
copy "C:\ProgramData\PyLiRP\*" "C:\Backup\PyLiRP\$(Get-Date -Format 'yyyy-MM-dd')\"

# Restore
copy "C:\Backup\PyLiRP\2024-01-01\*" "C:\ProgramData\PyLiRP\"
```

### Log Rotation
Windows log rotation is handled by the application. Configure in `config.yaml`:
```yaml
logging:
  file:
    max_size: 10MB
    rotate_count: 5
```

## 🆘 Support

### System Information Collection
```powershell
# Collect system info for support
systeminfo > pyslirp_sysinfo.txt
sc query PyLiRP >> pyslirp_sysinfo.txt
Get-EventLog -LogName Application -Source PyLiRP -Newest 50 >> pyslirp_sysinfo.txt
```

### Remote Support
For remote debugging, PyLiRP provides web interfaces and can integrate with Windows Remote Management (WinRM).

---

## 📞 Windows-Specific Support

- **Windows Event Logs**: Check Application log for PyLiRP events  
- **Performance Monitor**: Use perfmon.exe to monitor PyLiRP performance
- **Service Manager**: Use services.msc for service management
- **Device Manager**: Use devmgmt.msc for COM port management

**PyLiRP on Windows** - Native Windows integration with enterprise features! 🪟🔗