# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
- Run all tests: `python -m unittest src/strongbus/test_core.py`
- Run tests with tox (across multiple Python versions): `tox`
- Install tox with uv: `uv tool install tox --with tox-uv`

### Building
- Build package: `python -m build`
- Build with tox: `tox -e build`

### Installation
- Development installation: `pip install -e .`
- Development installation with tox: `tox -e dev`

## Architecture Overview

StrongBus is a type-safe event bus library with three core components:

### Core Components (`src/strongbus/core.py`)
- **Event**: Base class for all events - simple data containers that inherit from Event
- **EventBus**: Central hub managing subscriptions and publishing events
  - Uses weak references for method callbacks (automatic cleanup)
  - Strong references for function callbacks (manual cleanup required)
  - Type-safe subscription system with generics
- **Enrollment**: Base class for objects that need to manage multiple event subscriptions
  - Tracks all subscriptions for easy bulk cleanup with `clear()`
  - Inherits from ABC and provides convenient subscription management

### Key Design Patterns
- **Type Safety**: Callbacks are typed to receive specific event types using generics
- **Memory Management**: Automatic cleanup of dead method references via `weakref.WeakMethod`
- **Event Isolation**: Events don't propagate to parent/child types - exact type matching only
- **Subscription Tracking**: Enrollment pattern allows bulk unsubscription

### Project Structure
- `src/strongbus/__init__.py`: Public API exports (EventBus, Event, Enrollment)
- `src/strongbus/core.py`: Core implementation (108 lines)
- `src/strongbus/test_core.py`: Comprehensive test suite
- `src/strongbus/py.typed`: Type hint marker for mypy

### Dependencies
- Zero runtime dependencies (pure Python)
- Development dependencies: tox, build, pytest-cov (defined in pyproject.toml)
- Supports Python 3.10+ (as specified in pyproject.toml)

### Testing Strategy
- Uses Python's built-in unittest framework
- Mock objects for testing callbacks
- Tests cover weak reference cleanup, type isolation, and memory management
- Tox configuration tests against Python 3.10, 3.11, 3.12, 3.13