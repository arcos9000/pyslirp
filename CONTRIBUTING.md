# Contributing to PyLiRP

Thank you for your interest in contributing to PyLiRP! This document provides guidelines and information for contributors.

## 🎯 Project Goals

PyLiRP aims to provide a robust, secure, and high-performance userspace implementation of SLiRP that:
- Operates entirely without root privileges
- Maintains RFC compliance (PPP, TCP/IP)
- Provides production-ready reliability and monitoring
- Supports both Windows and Linux platforms

## 🚀 Getting Started

### Development Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/pyslirp.git
   cd pyslirp
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   # Windows additionally:
   pip install -r requirements_windows.txt
   ```

3. **Run tests**:
   ```bash
   python test_framework.py
   ```

### Code Structure

- `main.py` - Application entry point and integration
- `pySLiRP.py` - Core PPP/TCP implementation
- `config_manager.py` - Configuration management
- `security.py` - Security and access control
- `monitoring.py` - Metrics and observability
- `error_recovery.py` - Error handling and resilience
- `windows_support.py` - Windows platform integration

## 📋 Development Guidelines

### Code Style

- Follow PEP 8 for Python code style
- Use type hints for all function signatures
- Include comprehensive docstrings for public methods
- Maintain 4-space indentation
- Keep line length under 100 characters

### Documentation

- Update README.md for user-facing changes
- Add docstrings for all new public methods
- Include inline comments for complex logic
- Update CLAUDE.md for architectural changes

### Testing

- Write unit tests for new functionality
- Include integration tests for end-to-end features
- Ensure all tests pass before submitting
- Maintain test coverage above 80%

### Commit Messages

Use clear, descriptive commit messages:
```
Add TCP window scaling support

- Implement RFC 1323 window scaling negotiation
- Add configuration option for window scale factor
- Include tests for various window sizes
- Update documentation with new config parameter
```

## 🧪 Testing

### Running Tests

```bash
# Run all tests
python test_framework.py

# Run specific test category
python -c "
import asyncio
from test_framework import *

async def run_tests():
    framework = TestFramework()
    suite = SecurityTestSuite(framework)
    await framework.run_test('Security Tests', suite.test_rate_limiting)

asyncio.run(run_tests())
"
```

### Test Categories

1. **Unit Tests** - Individual component testing
2. **Integration Tests** - End-to-end functionality
3. **Performance Tests** - Load and throughput testing
4. **Compliance Tests** - RFC protocol compliance
5. **Security Tests** - Attack simulation and mitigation

### Adding New Tests

When adding new functionality:

1. Create unit tests for the component
2. Add integration tests if it affects the data flow
3. Include performance tests for performance-critical code
4. Add security tests for security-related features

## 🔒 Security Considerations

### Security-First Development

- Never disable security features by default
- Validate all input from external sources (serial, network)
- Use principle of least privilege
- Log security-relevant events
- Consider denial-of-service implications

### Security Review Process

Security-related changes require:

1. Detailed security analysis in PR description
2. Consideration of attack vectors
3. Performance impact assessment
4. Documentation of security implications

## 🐛 Bug Reports

### Before Reporting

1. Check existing issues
2. Test with the latest version
3. Verify it's not a configuration issue
4. Collect debug information

### Bug Report Template

```markdown
**Bug Description**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Configure PyLiRP with...
2. Run command...
3. Observe error...

**Expected Behavior**
What you expected to happen.

**Environment:**
- OS: [e.g., Windows 10, Ubuntu 20.04]
- Python Version: [e.g., 3.9.0]
- PyLiRP Version: [e.g., 1.0.0]
- Serial Device: [e.g., COM1, /dev/ttyUSB0]

**Configuration**
```yaml
# Include relevant config.yaml sections
```

**Logs**
```
# Include relevant log output
```

**Additional Context**
Any other context about the problem.
```

## 💡 Feature Requests

### Before Requesting

1. Check if similar functionality exists
2. Consider if it fits the project goals
3. Think about implementation complexity
4. Consider security implications

### Feature Request Template

```markdown
**Feature Description**
A clear description of what you want to happen.

**Use Case**
Describe the problem this feature would solve.

**Proposed Implementation**
If you have ideas about how to implement this.

**Alternatives Considered**
Other solutions you've considered.

**Additional Context**
Any other context about the feature request.
```

## 🔄 Pull Request Process

### Before Submitting

1. **Fork the repository** and create a feature branch
2. **Make your changes** following the coding guidelines
3. **Add or update tests** as needed
4. **Update documentation** if applicable
5. **Run all tests** and ensure they pass
6. **Check code style** and fix any issues

### Pull Request Template

```markdown
## Summary
Brief description of changes made.

## Changes Made
- List of specific changes
- Include new features, bug fixes, etc.

## Testing
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] Manual testing completed

## Documentation
- [ ] Documentation updated if needed
- [ ] Configuration changes documented
- [ ] Breaking changes noted

## Security Review
- [ ] No new security vulnerabilities introduced
- [ ] Security implications considered
- [ ] Input validation added where needed

## Platform Testing
- [ ] Tested on Linux
- [ ] Tested on Windows (if applicable)
- [ ] Cross-platform compatibility verified
```

### Review Process

1. **Automated checks** must pass
2. **Code review** by maintainer(s)
3. **Testing** on multiple platforms if needed
4. **Security review** for security-related changes
5. **Documentation review** for user-facing changes

## 📞 Getting Help

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and discussions
- **Code Reviews**: Technical discussions in pull requests

### Response Times

- We aim to respond to issues within 48 hours
- Pull requests are typically reviewed within one week
- Security issues receive priority attention

## 🙏 Recognition

Contributors are recognized in:
- README.md contributors section
- Git commit history
- Release notes for significant contributions

## 📄 License

By contributing to PyLiRP, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to PyLiRP! 🐍🔗