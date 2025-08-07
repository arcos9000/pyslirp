# Changelog

All notable changes to PyLiRP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-08-07

### Added
- Initial release of PyLiRP - Python SLiRP implementation
- Complete userspace PPP over serial implementation
- RFC 1661/1332 compliant PPP negotiation (LCP/IPCP)
- RFC 793 compliant TCP state machine with congestion control
- Cross-platform support (Windows and Linux)
- Comprehensive configuration management system
- Security framework with rate limiting and access control
- Connection pooling with LRU cache and health monitoring
- Error recovery with circuit breakers and automatic retry
- Monitoring framework with Prometheus metrics
- Windows-specific userspace installation and service management
- Comprehensive testing framework
- SOCKS5 proxy support

### Windows Features
- Task Scheduler integration for userspace service management
- COM port auto-detection and configuration
- Portable installation mode (no admin privileges required)
- Windows performance optimizations
- PowerShell installation scripts

### Security Features
- Token bucket rate limiting
- IP-based access control with allow/block lists
- Per-service and global connection limits
- Brute force attack detection and automatic blocking
- Comprehensive security audit logging
- Circuit breaker pattern for service protection

### Monitoring Features
- Prometheus metrics endpoint (/metrics)
- Health check endpoint (/health)
- Real-time connection statistics
- Performance metrics (latency, throughput, packet processing)
- Packet capture support for debugging
- Component health tracking

### Configuration
- YAML-based configuration with validation
- Environment variable overrides
- Hot-reload support for non-disruptive updates
- Default configurations for common use cases
- Platform-specific configuration templates

### Documentation
- Comprehensive README with installation guides
- Architecture documentation in CLAUDE.md
- Contributing guidelines
- Windows-specific documentation
- Troubleshooting guides

## [1.1.0] - 2024-08-07

### Major Release: Enhanced Installation & Virtual Environment Support

### Added
- **Virtual Environment Support**: All installations now use isolated Python environments
- **Multi-Distro Linux Support**: Added support for 10+ package managers
  - APT (Debian/Ubuntu), DNF (Fedora/RHEL 8+), YUM (RHEL/CentOS 7)
  - Pacman (Arch), Zypper (openSUSE), APK (Alpine), Portage (Gentoo)
  - XBPS (Void Linux), PKG (FreeBSD)
- **Windows Scoop Integration**: Modern package manager support with auto-installation
- **Smart Python Management**: Auto-detection and installation of Python 3.8+
- **Enhanced Installers**:
  - `install_linux_venv.sh` - Comprehensive Linux installer with venv support
  - `install_windows_venv.ps1` - Windows installer with Scoop + venv integration
  - `install_pyslirp.sh/.bat` - Unified launcher scripts
- **Development Dependencies**: Added `requirements-dev.txt` for development setup
- **Project Archive**: Moved obsolete files to `.archive/` with documentation

### Improved
- **Installation Experience**: Streamlined, automatic, cross-platform
- **Dependency Management**: Clear separation of required vs optional packages
- **Error Handling**: Enhanced troubleshooting and recovery mechanisms
- **Documentation**: Comprehensive virtual environment guides and troubleshooting
- **Service Integration**: Virtual environment support in systemd and Windows services
- **Python Detection**: Better handling of multiple Python versions

### Fixed
- RecoveryAction.RESTART error (changed to RecoveryAction.RESET)
- Windows firewall rule issues in userspace mode
- PowerShell script execution and error reporting
- Virtual environment privilege handling with sudo/admin
- COM port detection and permissions on Windows

### Changed
- **Project Structure**: Organized files into logical categories
- **Installation Methods**: Replaced legacy installers with venv-aware versions
- **Requirements**: Updated and clarified package dependencies
- **Documentation**: Integrated platform-specific guides into main README

### Deprecated
- Legacy installers (moved to .archive/ for reference)
- Global Python package installation (replaced with virtual environments)

### Security
- Enhanced userspace operation with no global system modifications
- Improved isolation of dependencies in virtual environments
- Better privilege handling for installation and service management

## [Unreleased]

### Planned Features
- IPv6 support (PPPv6)
- UDP protocol support
- HTTP/HTTPS proxy protocol support
- ICMP (ping) support
- Van Jacobson and Deflate compression
- Docker container support
- GUI configuration interface
- Mobile device support (Android/iOS)

### Known Issues
- None at this time

---

## Release Notes

### v1.0.0 Release Highlights

This initial release provides a complete, production-ready Python implementation of SLiRP that operates entirely in userspace. Key achievements:

**Complete Userspace Operation**: No root privileges required, no kernel modifications, all networking operations isolated in Python memory.

**Cross-Platform Support**: Full Windows and Linux support with platform-specific optimizations and installation methods.

**Production Ready**: Comprehensive error recovery, monitoring, security, and configuration management suitable for production deployments.

**Windows Focus**: Special attention to Windows userspace deployment with Task Scheduler integration, COM port management, and no-admin-required installation.

**Security First**: Built-in security features including rate limiting, access control, and attack mitigation suitable for network-exposed deployments.

**Monitoring & Observability**: Complete monitoring framework with metrics, health checks, and debugging capabilities for operational excellence.

This release represents a complete rewrite and enhancement of the original SLiRP concept, bringing modern Python capabilities to userspace networking.