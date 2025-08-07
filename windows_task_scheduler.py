#!/usr/bin/env python3
"""
Windows Task Scheduler Integration for PyLiRP
Provides userspace alternative to Windows services using Task Scheduler
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any
import xml.etree.ElementTree as ET
from datetime import datetime

logger = logging.getLogger(__name__)

class WindowsTaskManager:
    """Manages Windows Scheduled Tasks for PyLiRP"""
    
    def __init__(self, platform_manager):
        self.platform_manager = platform_manager
        self.task_name = "PyLiRP-UserSpace"
        self.task_folder = "\\PyLiRP\\"
        
    def create_task_xml(self, script_path: str, config_path: str, 
                       working_dir: str, user_context: bool = True) -> str:
        """Create Windows Task XML definition"""
        
        current_user = os.environ.get('USERNAME', 'User')
        computer_name = os.environ.get('COMPUTERNAME', 'localhost')
        
        # Use current user if in user context, otherwise use system
        principal = f"{computer_name}\\{current_user}" if user_context else "SYSTEM"
        
        xml_template = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{datetime.now().isoformat()}</Date>
    <Author>{current_user}</Author>
    <Description>Python SLiRP PPP Bridge - Userspace Implementation</Description>
    <URI>\\PyLiRP\\PyLiRP-UserSpace</URI>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </BootTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{principal}</UserId>
      <Delay>PT15S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{principal}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
    <RestartPolicy>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartPolicy>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>python.exe</Command>
      <Arguments>"{script_path}" --config "{config_path}" --daemon</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
        
        return xml_template
    
    async def install_task(self, script_path: str, config_path: str, 
                          working_dir: str, user_context: bool = True) -> bool:
        """Install PyLiRP as a Windows Scheduled Task"""
        try:
            logger.info(f"Installing Windows Scheduled Task: {self.task_name}")
            
            # Create task XML
            task_xml = self.create_task_xml(script_path, config_path, working_dir, user_context)
            
            # Save XML to temp file
            temp_xml = os.path.join(os.environ.get('TEMP', 'C:\\Windows\\Temp'), 'pyslirp_task.xml')
            with open(temp_xml, 'w', encoding='utf-16') as f:
                f.write(task_xml)
            
            # Create task using schtasks command
            cmd = [
                'schtasks', '/create',
                '/tn', self.task_name,
                '/xml', temp_xml,
                '/f'  # Force overwrite if exists
            ]
            
            if not user_context:
                cmd.extend(['/ru', 'SYSTEM'])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Clean up temp file
            try:
                os.remove(temp_xml)
            except:
                pass
            
            logger.info("Scheduled task installed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install scheduled task: {e}")
            logger.error(f"Command output: {e.stdout}")
            logger.error(f"Command error: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error installing scheduled task: {e}")
            return False
    
    async def uninstall_task(self) -> bool:
        """Uninstall PyLiRP Scheduled Task"""
        try:
            cmd = ['schtasks', '/delete', '/tn', self.task_name, '/f']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            logger.info("Scheduled task uninstalled successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to uninstall scheduled task: {e}")
            return False
        except Exception as e:
            logger.error(f"Error uninstalling scheduled task: {e}")
            return False
    
    def is_task_installed(self) -> bool:
        """Check if PyLiRP task is installed"""
        try:
            cmd = ['schtasks', '/query', '/tn', self.task_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    def get_task_status(self) -> Optional[str]:
        """Get task status"""
        try:
            cmd = ['schtasks', '/query', '/tn', self.task_name, '/fo', 'csv']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse CSV output (skip header)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                # Extract status from CSV line
                fields = lines[1].split(',')
                if len(fields) > 3:
                    status = fields[3].strip('"')
                    return status.lower()
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get task status: {e}")
            return None
    
    async def start_task(self) -> bool:
        """Start the scheduled task"""
        try:
            cmd = ['schtasks', '/run', '/tn', self.task_name]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            logger.info("Scheduled task started")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start scheduled task: {e}")
            return False
        except Exception as e:
            logger.error(f"Error starting scheduled task: {e}")
            return False
    
    async def stop_task(self) -> bool:
        """Stop the scheduled task"""
        try:
            # Find and terminate PyLiRP processes
            cmd = ['taskkill', '/f', '/im', 'python.exe', '/fi', 'WINDOWTITLE eq PyLiRP*']
            subprocess.run(cmd, capture_output=True, text=True)
            
            # More targeted approach - find processes with our script
            cmd = ['wmic', 'process', 'where', 'commandline like "%pySLiRP%"', 'delete']
            subprocess.run(cmd, capture_output=True, text=True)
            
            logger.info("PyLiRP processes terminated")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping task: {e}")
            return False
    
    def enable_task(self) -> bool:
        """Enable the scheduled task"""
        try:
            cmd = ['schtasks', '/change', '/tn', self.task_name, '/enable']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except:
            return False
    
    def disable_task(self) -> bool:
        """Disable the scheduled task"""
        try:
            cmd = ['schtasks', '/change', '/tn', self.task_name, '/disable']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except:
            return False
    
    def get_task_info(self) -> Dict[str, Any]:
        """Get detailed task information"""
        try:
            cmd = ['schtasks', '/query', '/tn', self.task_name, '/xml']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse XML
            root = ET.fromstring(result.stdout)
            
            info = {
                'name': self.task_name,
                'status': self.get_task_status(),
                'installed': True
            }
            
            # Extract key information from XML
            try:
                # Get triggers
                triggers = []
                for trigger in root.findall('.//Triggers/*'):
                    triggers.append(trigger.tag)
                info['triggers'] = triggers
                
                # Get command
                command_elem = root.find('.//Command')
                if command_elem is not None:
                    info['command'] = command_elem.text
                
                # Get arguments
                args_elem = root.find('.//Arguments')
                if args_elem is not None:
                    info['arguments'] = args_elem.text
                
                # Get working directory
                workdir_elem = root.find('.//WorkingDirectory')
                if workdir_elem is not None:
                    info['working_directory'] = workdir_elem.text
                    
            except Exception as e:
                logger.debug(f"Could not parse task XML details: {e}")
            
            return info
            
        except Exception as e:
            logger.debug(f"Could not get task info: {e}")
            return {
                'name': self.task_name,
                'status': 'unknown',
                'installed': False
            }

class WindowsStartupManager:
    """Manages Windows startup methods for PyLiRP"""
    
    def __init__(self, platform_manager):
        self.platform_manager = platform_manager
        
    def add_to_startup_folder(self, script_path: str, config_path: str) -> bool:
        """Add PyLiRP shortcut to Windows startup folder"""
        try:
            import winshell
            from win32com.client import Dispatch
            
            startup_folder = winshell.startup()
            shortcut_path = os.path.join(startup_folder, "PyLiRP.lnk")
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = sys.executable
            shortcut.Arguments = f'"{script_path}" --config "{config_path}" --daemon'
            shortcut.WorkingDirectory = os.path.dirname(script_path)
            shortcut.IconLocation = sys.executable
            shortcut.Description = "Python SLiRP PPP Bridge"
            shortcut.save()
            
            logger.info("Added to Windows startup folder")
            return True
            
        except ImportError:
            logger.warning("winshell not available for startup folder management")
            return False
        except Exception as e:
            logger.error(f"Failed to add to startup folder: {e}")
            return False
    
    def remove_from_startup_folder(self) -> bool:
        """Remove PyLiRP from Windows startup folder"""
        try:
            import winshell
            
            startup_folder = winshell.startup()
            shortcut_path = os.path.join(startup_folder, "PyLiRP.lnk")
            
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                logger.info("Removed from Windows startup folder")
                return True
            else:
                logger.info("Not found in startup folder")
                return True
                
        except ImportError:
            logger.warning("winshell not available")
            return False
        except Exception as e:
            logger.error(f"Failed to remove from startup folder: {e}")
            return False
    
    def add_to_registry_run(self, script_path: str, config_path: str, 
                           current_user_only: bool = True) -> bool:
        """Add PyLiRP to Windows Registry Run key"""
        try:
            import winreg
            
            # Choose registry hive
            if current_user_only:
                hive = winreg.HKEY_CURRENT_USER
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            else:
                hive = winreg.HKEY_LOCAL_MACHINE
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            # Open registry key
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
            
            # Set value
            command = f'"{sys.executable}" "{script_path}" --config "{config_path}" --daemon'
            winreg.SetValueEx(key, "PyLiRP", 0, winreg.REG_SZ, command)
            winreg.CloseKey(key)
            
            logger.info(f"Added to registry run key ({'HKCU' if current_user_only else 'HKLM'})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add to registry: {e}")
            return False
    
    def remove_from_registry_run(self, current_user_only: bool = True) -> bool:
        """Remove PyLiRP from Windows Registry Run key"""
        try:
            import winreg
            
            # Choose registry hive
            if current_user_only:
                hive = winreg.HKEY_CURRENT_USER
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            else:
                hive = winreg.HKEY_LOCAL_MACHINE
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            # Open registry key
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
            
            try:
                winreg.DeleteValue(key, "PyLiRP")
                logger.info("Removed from registry run key")
            except FileNotFoundError:
                logger.info("Not found in registry run key")
            
            winreg.CloseKey(key)
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove from registry: {e}")
            return False

class WindowsUserSpaceManager:
    """Main Windows userspace management"""
    
    def __init__(self, platform_manager):
        self.platform_manager = platform_manager
        self.task_manager = WindowsTaskManager(platform_manager)
        self.startup_manager = WindowsStartupManager(platform_manager)
    
    async def install_userspace_service(self, script_path: str, config_path: str,
                                       method: str = 'task') -> bool:
        """Install PyLiRP using userspace methods"""
        working_dir = os.path.dirname(script_path)
        
        if method == 'task':
            # Use Task Scheduler (preferred)
            return await self.task_manager.install_task(
                script_path, config_path, working_dir, user_context=True
            )
        elif method == 'startup':
            # Use startup folder
            return self.startup_manager.add_to_startup_folder(script_path, config_path)
        elif method == 'registry':
            # Use registry run key
            return self.startup_manager.add_to_registry_run(
                script_path, config_path, current_user_only=True
            )
        else:
            logger.error(f"Unknown installation method: {method}")
            return False
    
    async def uninstall_userspace_service(self, method: str = 'task') -> bool:
        """Uninstall PyLiRP userspace service"""
        if method == 'task':
            return await self.task_manager.uninstall_task()
        elif method == 'startup':
            return self.startup_manager.remove_from_startup_folder()
        elif method == 'registry':
            return self.startup_manager.remove_from_registry_run(current_user_only=True)
        else:
            return False
    
    async def start_userspace_service(self, method: str = 'task') -> bool:
        """Start PyLiRP userspace service"""
        if method == 'task':
            return await self.task_manager.start_task()
        else:
            logger.info("Manual start required for this installation method")
            return False
    
    async def stop_userspace_service(self, method: str = 'task') -> bool:
        """Stop PyLiRP userspace service"""
        if method == 'task':
            return await self.task_manager.stop_task()
        else:
            # Generic process termination
            try:
                cmd = ['taskkill', '/f', '/im', 'python.exe', '/fi', 'WINDOWTITLE eq PyLiRP*']
                subprocess.run(cmd, capture_output=True, text=True)
                return True
            except:
                return False
    
    def get_service_status(self, method: str = 'task') -> Dict[str, Any]:
        """Get userspace service status"""
        if method == 'task':
            return self.task_manager.get_task_info()
        else:
            return {
                'method': method,
                'status': 'unknown',
                'installed': False
            }
    
    def is_service_installed(self, method: str = 'task') -> bool:
        """Check if userspace service is installed"""
        if method == 'task':
            return self.task_manager.is_task_installed()
        elif method == 'startup':
            try:
                import winshell
                startup_folder = winshell.startup()
                return os.path.exists(os.path.join(startup_folder, "PyLiRP.lnk"))
            except:
                return False
        elif method == 'registry':
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                   r"Software\Microsoft\Windows\CurrentVersion\Run")
                try:
                    winreg.QueryValueEx(key, "PyLiRP")
                    winreg.CloseKey(key)
                    return True
                except FileNotFoundError:
                    winreg.CloseKey(key)
                    return False
            except:
                return False
        else:
            return False