#!/usr/bin/env python3
"""
Windows Support Module for PyLiRP
Provides Windows-specific functionality including service management, 
COM port handling, and Windows-specific optimizations
"""

import asyncio
import logging
import platform
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import subprocess
import json

# Windows-specific imports (conditionally imported)
if platform.system() == 'Windows':
    import winsound
    try:
        import winreg
        import win32service
        import win32serviceutil
        import win32event
        import win32api
        import servicemanager
        HAS_WIN32 = True
    except ImportError:
        HAS_WIN32 = False
        logging.warning("pywin32 not available - some Windows features disabled")
else:
    HAS_WIN32 = False

logger = logging.getLogger(__name__)

class WindowsPlatformManager:
    """Manages Windows-specific platform features"""
    
    def __init__(self):
        self.is_windows = platform.system() == 'Windows'
        self.has_win32 = HAS_WIN32
        self.windows_version = None
        self.admin_privileges = False
        
        if self.is_windows:
            self._detect_windows_version()
            self._check_admin_privileges()
    
    def _detect_windows_version(self):
        """Detect Windows version and capabilities"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                               r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            
            self.windows_version = {
                'product_name': winreg.QueryValueEx(key, "ProductName")[0],
                'current_build': winreg.QueryValueEx(key, "CurrentBuild")[0],
                'release_id': winreg.QueryValueEx(key, "ReleaseId")[0] if self._reg_value_exists(key, "ReleaseId") else "Unknown"
            }
            winreg.CloseKey(key)
            
            logger.info(f"Windows version detected: {self.windows_version['product_name']} "
                       f"Build {self.windows_version['current_build']}")
                       
        except Exception as e:
            logger.warning(f"Could not detect Windows version: {e}")
            self.windows_version = {"product_name": "Windows", "current_build": "Unknown"}
    
    def _reg_value_exists(self, key, value_name):
        """Check if registry value exists"""
        try:
            winreg.QueryValueEx(key, value_name)
            return True
        except FileNotFoundError:
            return False
    
    def _check_admin_privileges(self):
        """Check if running with administrator privileges"""
        try:
            import ctypes
            self.admin_privileges = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            # Fallback method
            try:
                with open(os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'temp', 'test_admin'), 'w') as f:
                    f.write('test')
                os.remove(os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'temp', 'test_admin'))
                self.admin_privileges = True
            except:
                self.admin_privileges = False
        
        logger.info(f"Administrator privileges: {'Yes' if self.admin_privileges else 'No'}")
    
    def get_com_ports(self) -> List[Dict[str, str]]:
        """Get available COM ports on Windows"""
        if not self.is_windows:
            return []
        
        ports = []
        
        try:
            # Method 1: Using registry
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            
            i = 0
            while True:
                try:
                    port_name, port_device, _ = winreg.EnumValue(key, i)
                    ports.append({
                        'device': port_device,
                        'name': port_name,
                        'description': f'Serial Port ({port_device})'
                    })
                    i += 1
                except OSError:
                    break
            
            winreg.CloseKey(key)
            
        except Exception as e:
            logger.debug(f"Registry method failed: {e}")
            
            # Method 2: Using WMI (fallback)
            try:
                import wmi
                c = wmi.WMI()
                for port in c.Win32_SerialPort():
                    ports.append({
                        'device': port.DeviceID,
                        'name': port.Name or port.DeviceID,
                        'description': port.Description or 'Serial Port'
                    })
            except ImportError:
                logger.debug("WMI not available for COM port detection")
            except Exception as e:
                logger.debug(f"WMI method failed: {e}")
        
        # Method 3: Simple enumeration (fallback)
        if not ports:
            for i in range(1, 21):  # Check COM1 through COM20
                port_name = f"COM{i}"
                try:
                    import serial
                    with serial.Serial(port_name, timeout=0) as ser:
                        pass
                    ports.append({
                        'device': port_name,
                        'name': port_name,
                        'description': f'Serial Port ({port_name})'
                    })
                except:
                    continue
        
        logger.info(f"Found {len(ports)} COM ports")
        return ports
    
    def get_default_paths(self, portable: bool = False, admin_mode: bool = None) -> Dict[str, str]:
        """Get Windows-specific default paths"""
        if not self.is_windows:
            return {}
        
        if admin_mode is None:
            admin_mode = self.admin_privileges
            
        if portable or not admin_mode:
            # Portable/user mode - use user directories
            home_dir = os.path.expanduser('~')
            appdata = os.environ.get('APPDATA', os.path.join(home_dir, 'AppData', 'Roaming'))
            
            return {
                'install_dir': os.path.join(home_dir, 'PyLiRP'),
                'config_dir': os.path.join(appdata, 'PyLiRP'),
                'log_dir': os.path.join(appdata, 'PyLiRP', 'logs'),
                'data_dir': os.path.join(appdata, 'PyLiRP', 'data'),
                'temp_dir': os.environ.get('TEMP', os.path.join(home_dir, 'AppData', 'Local', 'Temp')),
                'task_config': os.path.join(appdata, 'PyLiRP', 'task_config.json')
            }
        else:
            # Admin mode - use system directories (fallback only)
            programdata = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
            
            return {
                'install_dir': os.path.join(programdata, 'PyLiRP'),
                'config_dir': os.path.join(programdata, 'PyLiRP'),
                'log_dir': os.path.join(programdata, 'PyLiRP', 'logs'),
                'data_dir': os.path.join(programdata, 'PyLiRP', 'data'),
                'temp_dir': os.environ.get('TEMP', 'C:\\Windows\\Temp'),
                'task_config': os.path.join(programdata, 'PyLiRP', 'task_config.json')
            }
    
    def is_service_installed(self, service_name: str = "PyLiRP") -> bool:
        """Check if Windows service is installed"""
        if not self.has_win32:
            return False
        
        try:
            win32serviceutil.QueryServiceStatus(service_name)
            return True
        except Exception:
            return False
    
    def get_service_status(self, service_name: str = "PyLiRP") -> Optional[str]:
        """Get Windows service status"""
        if not self.has_win32:
            return None
        
        try:
            status = win32serviceutil.QueryServiceStatus(service_name)
            status_map = {
                win32service.SERVICE_STOPPED: 'stopped',
                win32service.SERVICE_START_PENDING: 'starting',
                win32service.SERVICE_STOP_PENDING: 'stopping', 
                win32service.SERVICE_RUNNING: 'running',
                win32service.SERVICE_CONTINUE_PENDING: 'resuming',
                win32service.SERVICE_PAUSE_PENDING: 'pausing',
                win32service.SERVICE_PAUSED: 'paused'
            }
            return status_map.get(status[1], 'unknown')
        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            return None

class WindowsServiceManager:
    """Windows service management (admin mode only)"""
    
    def __init__(self, platform_manager: WindowsPlatformManager):
        self.platform_manager = platform_manager
        self.service_name = "PyLiRP"
        self.service_display_name = "Python SLiRP PPP Bridge"
        self.service_description = "Provides PPP over serial connectivity to local services"
        
        # Import userspace task scheduler
        try:
            from windows_task_scheduler import WindowsUserSpaceManager
            self.userspace_manager = WindowsUserSpaceManager(platform_manager)
        except ImportError:
            self.userspace_manager = None
    
    async def install_service(self, script_path: str, config_path: str, 
                             userspace: bool = False, method: str = 'task') -> bool:
        """Install Windows service or userspace equivalent"""
        
        # If userspace mode or no admin privileges, use userspace manager
        if userspace or not self.platform_manager.admin_privileges:
            if self.userspace_manager:
                logger.info("Installing userspace service using method: " + method)
                return await self.userspace_manager.install_userspace_service(
                    script_path, config_path, method
                )
            else:
                logger.error("Userspace manager not available")
                return False
        
        # Admin mode - traditional Windows service
        if not self.platform_manager.has_win32:
            logger.error("pywin32 required for Windows service installation")
            return False
        
        if not self.platform_manager.admin_privileges:
            logger.error("Administrator privileges required for service installation")
            return False
        
        try:
            # Create service configuration
            service_config = {
                'script_path': script_path,
                'config_path': config_path,
                'service_name': self.service_name,
                'display_name': self.service_display_name,
                'description': self.service_description
            }
            
            # Save service configuration
            paths = self.platform_manager.get_default_paths()
            os.makedirs(os.path.dirname(paths['service_config']), exist_ok=True)
            
            with open(paths['service_config'], 'w') as f:
                json.dump(service_config, f, indent=2)
            
            # Install service
            win32serviceutil.InstallService(
                None,  # Service class
                self.service_name,
                self.service_display_name,
                startType=win32service.SERVICE_AUTO_START,
                description=self.service_description,
                exeName=sys.executable,
                exeArgs=f'"{script_path}" --config "{config_path}" --service'
            )
            
            logger.info(f"Service '{self.service_name}' installed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install service: {e}")
            return False
    
    async def uninstall_service(self) -> bool:
        """Uninstall Windows service"""
        if not self.platform_manager.has_win32:
            return False
        
        try:
            win32serviceutil.RemoveService(self.service_name)
            logger.info(f"Service '{self.service_name}' uninstalled successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to uninstall service: {e}")
            return False
    
    async def start_service(self) -> bool:
        """Start Windows service"""
        if not self.platform_manager.has_win32:
            return False
        
        try:
            win32serviceutil.StartService(self.service_name)
            logger.info(f"Service '{self.service_name}' started")
            return True
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return False
    
    async def stop_service(self) -> bool:
        """Stop Windows service"""
        if not self.platform_manager.has_win32:
            return False
        
        try:
            win32serviceutil.StopService(self.service_name)
            logger.info(f"Service '{self.service_name}' stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop service: {e}")
            return False

class WindowsFirewallManager:
    """Windows Firewall management"""
    
    def __init__(self, platform_manager: WindowsPlatformManager):
        self.platform_manager = platform_manager
    
    async def add_firewall_rule(self, name: str, port: int, protocol: str = 'TCP') -> bool:
        """Add Windows Firewall rule"""
        if not self.platform_manager.is_windows:
            return False
        
        try:
            # Use netsh command to add firewall rule
            cmd = [
                'netsh', 'advfirewall', 'firewall', 'add', 'rule',
                f'name={name}',
                'dir=in',
                'action=allow',
                f'protocol={protocol}',
                f'localport={port}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Firewall rule added: {name} ({protocol}/{port})")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add firewall rule: {e}")
            return False
        except Exception as e:
            logger.error(f"Firewall rule error: {e}")
            return False
    
    async def remove_firewall_rule(self, name: str) -> bool:
        """Remove Windows Firewall rule"""
        if not self.platform_manager.is_windows:
            return False
        
        try:
            cmd = ['netsh', 'advfirewall', 'firewall', 'delete', 'rule', f'name={name}']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Firewall rule removed: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove firewall rule: {e}")
            return False

class WindowsPerformanceOptimizer:
    """Windows-specific performance optimizations"""
    
    def __init__(self, platform_manager: WindowsPlatformManager):
        self.platform_manager = platform_manager
    
    def optimize_serial_settings(self, port: str) -> Dict[str, Any]:
        """Get optimized serial port settings for Windows"""
        settings = {
            'port': port,
            'baudrate': 115200,
            'bytesize': 8,
            'parity': 'N',
            'stopbits': 1,
            'timeout': 1,
            'write_timeout': 1,
            'inter_byte_timeout': None,
            'exclusive': True,  # Windows-specific
        }
        
        # Windows-specific optimizations
        if self.platform_manager.is_windows:
            settings.update({
                'rtscts': True,  # Hardware flow control
                'dsrdtr': False,
                'xonxoff': False,  # No software flow control
            })
        
        return settings
    
    def get_buffer_sizes(self) -> Dict[str, int]:
        """Get optimized buffer sizes for Windows"""
        return {
            'read_buffer_size': 8192,
            'write_buffer_size': 8192,
            'tcp_window_size': 65536,
            'socket_buffer_size': 65536
        }
    
    def set_process_priority(self, priority: str = 'high') -> bool:
        """Set process priority on Windows"""
        if not self.platform_manager.is_windows:
            return False
        
        try:
            import psutil
            process = psutil.Process()
            
            priority_map = {
                'low': psutil.BELOW_NORMAL_PRIORITY_CLASS,
                'normal': psutil.NORMAL_PRIORITY_CLASS, 
                'high': psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                'realtime': psutil.REALTIME_PRIORITY_CLASS
            }
            
            if priority in priority_map:
                process.nice(priority_map[priority])
                logger.info(f"Process priority set to: {priority}")
                return True
                
        except Exception as e:
            logger.warning(f"Failed to set process priority: {e}")
            
        return False

class WindowsEventLogger:
    """Windows Event Log integration"""
    
    def __init__(self, platform_manager: WindowsPlatformManager):
        self.platform_manager = platform_manager
        self.app_name = "PyLiRP"
        self.event_log_setup = False
        
        if self.platform_manager.has_win32:
            self._setup_event_log()
    
    def _setup_event_log(self):
        """Setup Windows Event Log source"""
        try:
            import win32evtlogutil
            import win32evtlog
            
            # Register event log source
            win32evtlogutil.AddSourceToRegistry(
                self.app_name,
                msgDLL=None,
                eventLogType="Application"
            )
            
            self.event_log_setup = True
            logger.info("Windows Event Log integration enabled")
            
        except Exception as e:
            logger.warning(f"Could not setup Windows Event Log: {e}")
    
    def log_event(self, level: str, message: str, event_id: int = 1000):
        """Log event to Windows Event Log"""
        if not self.event_log_setup or not self.platform_manager.has_win32:
            return
        
        try:
            import win32evtlogutil
            import win32evtlog
            
            event_type_map = {
                'info': win32evtlog.EVENTLOG_INFORMATION_TYPE,
                'warning': win32evtlog.EVENTLOG_WARNING_TYPE,
                'error': win32evtlog.EVENTLOG_ERROR_TYPE
            }
            
            event_type = event_type_map.get(level.lower(), win32evtlog.EVENTLOG_INFORMATION_TYPE)
            
            win32evtlogutil.ReportEvent(
                self.app_name,
                event_id,
                eventType=event_type,
                strings=[message]
            )
            
        except Exception as e:
            logger.debug(f"Failed to log Windows event: {e}")

class WindowsServiceHandler(win32serviceutil.ServiceFramework if HAS_WIN32 else object):
    """Windows service handler for PyLiRP"""
    
    if HAS_WIN32:
        _svc_name_ = "PyLiRP"
        _svc_display_name_ = "Python SLiRP PPP Bridge"
        _svc_description_ = "Provides PPP over serial connectivity to local services"
    
    def __init__(self, args):
        if not HAS_WIN32:
            raise RuntimeError("Windows service requires pywin32")
            
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.app = None
        self.event_logger = WindowsEventLogger(WindowsPlatformManager())
    
    def SvcStop(self):
        """Handle service stop"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        
        if self.app:
            asyncio.create_task(self.app.shutdown())
        
        self.event_logger.log_event('info', 'PyLiRP service stopped')
    
    def SvcDoRun(self):
        """Handle service run"""
        try:
            self.event_logger.log_event('info', 'PyLiRP service starting')
            
            # Load service configuration
            platform_manager = WindowsPlatformManager()
            paths = platform_manager.get_default_paths()
            
            with open(paths['service_config'], 'r') as f:
                service_config = json.load(f)
            
            # Import and run application
            sys.path.insert(0, os.path.dirname(service_config['script_path']))
            from main import PyLiRPApplication
            
            self.app = PyLiRPApplication(service_config['config_path'])
            
            # Run in event loop
            asyncio.run(self.app.start())
            
        except Exception as e:
            self.event_logger.log_event('error', f'PyLiRP service error: {e}')
            logger.error(f"Service error: {e}")

class WindowsNotificationManager:
    """Windows notification system"""
    
    def __init__(self, platform_manager: WindowsPlatformManager):
        self.platform_manager = platform_manager
        self.notifications_enabled = platform_manager.is_windows
    
    def show_notification(self, title: str, message: str, icon: str = 'info'):
        """Show Windows notification"""
        if not self.notifications_enabled:
            return
        
        try:
            # Try Windows 10+ toast notifications
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
                return
            except ImportError:
                pass
            
            # Fallback to system beep + message box
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()  # Hide main window
            
            if icon == 'error':
                messagebox.showerror(title, message)
            elif icon == 'warning':
                messagebox.showwarning(title, message)
            else:
                messagebox.showinfo(title, message)
            
            root.destroy()
            
        except Exception as e:
            logger.debug(f"Failed to show notification: {e}")
            
            # Ultimate fallback - system beep
            try:
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
            except:
                pass

def get_windows_manager() -> Optional['WindowsManager']:
    """Get Windows manager instance if on Windows"""
    if platform.system() != 'Windows':
        return None
    
    return WindowsManager()

class WindowsManager:
    """Main Windows support manager"""
    
    def __init__(self):
        self.platform_manager = WindowsPlatformManager()
        self.service_manager = WindowsServiceManager(self.platform_manager)
        self.firewall_manager = WindowsFirewallManager(self.platform_manager)
        self.performance_optimizer = WindowsPerformanceOptimizer(self.platform_manager)
        self.event_logger = WindowsEventLogger(self.platform_manager)
        self.notification_manager = WindowsNotificationManager(self.platform_manager)
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive Windows system information"""
        info = {
            'platform': 'Windows',
            'is_windows': True,
            'has_win32': self.platform_manager.has_win32,
            'admin_privileges': self.platform_manager.admin_privileges,
            'windows_version': self.platform_manager.windows_version,
            'com_ports': self.platform_manager.get_com_ports(),
            'default_paths': self.platform_manager.get_default_paths(),
        }
        
        # Service information
        if self.platform_manager.has_win32:
            info['service'] = {
                'installed': self.platform_manager.is_service_installed(),
                'status': self.platform_manager.get_service_status()
            }
        
        return info
    
    async def setup_windows_environment(self, config: Dict[str, Any]) -> bool:
        """Setup Windows environment for PyLiRP"""
        try:
            logger.info("Setting up Windows environment...")
            
            # Create directories
            paths = self.platform_manager.get_default_paths()
            for path in paths.values():
                if path.endswith('.json'):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                else:
                    os.makedirs(path, exist_ok=True)
            
            # Setup firewall rules if needed
            if config.get('setup_firewall', True):
                await self.firewall_manager.add_firewall_rule(
                    "PyLiRP-Metrics", 9090, "TCP"
                )
                await self.firewall_manager.add_firewall_rule(
                    "PyLiRP-Health", 9091, "TCP"
                )
            
            # Optimize performance
            self.performance_optimizer.set_process_priority('high')
            
            logger.info("Windows environment setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Windows environment: {e}")
            return False
    
    async def install_as_service(self, script_path: str, config_path: str) -> bool:
        """Install PyLiRP as Windows service"""
        return await self.service_manager.install_service(script_path, config_path)
    
    async def uninstall_service(self) -> bool:
        """Uninstall PyLiRP Windows service"""
        return await self.service_manager.uninstall_service()
    
    def log_event(self, level: str, message: str):
        """Log event to Windows Event Log"""
        self.event_logger.log_event(level, message)
    
    def show_notification(self, title: str, message: str, icon: str = 'info'):
        """Show Windows notification"""
        self.notification_manager.show_notification(title, message, icon)

# Service entry point for Windows
if __name__ == '__main__':
    if HAS_WIN32 and len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WindowsServiceHandler)
        servicemanager.StartServiceCtrlDispatcher()
    elif HAS_WIN32:
        win32serviceutil.HandleCommandLine(WindowsServiceHandler)