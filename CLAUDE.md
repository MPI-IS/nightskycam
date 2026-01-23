# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nightskycam is a Python-based system for automated night sky photography. It controls cameras (ZWO ASI, USB webcams), manages apertures, processes images, and handles FTP uploads. Python 3.12+ required.

## Common Commands

```bash
# Install dependencies
poetry install

# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_cam_runner.py -v

# Run specific test function
poetry run pytest tests/test_cam_runner.py::test_function_name -v

# Format code
poetry run black nightskycam/ tests/

# Sort imports
poetry run isort nightskycam/ tests/

# Type checking
poetry run mypy nightskycam/

# Run application
poetry run nightskycam-start config/nightskycam.toml

# Stress test (detect intermittent issues)
poetry run nightskycam-repetitive-test -max-iterations 20 -run-for 5.0
```

## Architecture

### Manager + Runners Pattern

The system uses a concurrent runner architecture from the `nightskyrunner` library:

```
Manager (orchestrator)
  ├─ CamRunner (ProcessRunner)     - Takes pictures
  ├─ ImageProcessRunner            - Processes images
  ├─ SpaceKeeperRunner             - Manages disk space
  ├─ FtpRunner (ThreadRunner)      - Uploads to FTP
  ├─ LocationInfoRunner            - Fetches weather/location
  ├─ StatusRunner                  - Publishes status via WebSocket
  ├─ ApertureRunner                - Controls lens aperture
  ├─ CommandRunner                 - Executes web commands
  └─ ...other optional runners
```

**Runner types:**
- `ProcessRunner` - Heavy computational work (camera I/O, image processing)
- `ThreadRunner` - I/O-bound work (FTP uploads, WebSocket comms)

### Configuration System

TOML-based hierarchical configuration in `config/`:
- `nightskycam.toml` - Master config defining all runners
- Individual `*.toml` files - Per-runner configuration
- `vars.toml` - Variable substitutions

### Key Modules

- `nightskycam/cams/` - Camera base classes; implementations in `asicams/`, `usbcams/`, `dummycams/`
- `nightskycam/process/` - Image processing pipeline (debayer, dark frame subtraction, stretching, resize)
- `nightskycam/ftp/` - FTP upload functionality
- `nightskycam/status/` - WebSocket-based status monitoring
- `nightskycam/utils/test_utils.py` - Test fixtures (`ConfigTester`, `get_manager()`, `wait_for()`)

### Entry Point

`nightskycam/main.py:execute()` - Loads config, creates Manager, runs indefinitely.

## Testing

Tests are in `tests/` using pytest. Test utilities in `nightskycam/utils/test_utils.py` provide helpers for runner testing.

## Type Safety

The package is PEP 561 compliant (`py.typed` marker). Use mypy for type checking. External package stubs configured in `mypy.ini`.
