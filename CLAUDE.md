# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project is managed with `uv`. For tox, use a global install with the tox-uv plugin: `uv tool install tox --with tox-uv` (the plain `tox` from the dev extra does not include the plugin and fails on this tox.ini).

### Testing
- Run all tests: `uv run --extra dev pytest`
- With coverage (as CI does): `uv run --extra dev pytest --cov --cov-branch --cov-report=xml`
- Across Python 3.10–3.13: `tox`

### Linting and Type Checking
- Lint with ruff (auto-fix): `tox -e lint`
- Type check with ty: `tox -e ty`

### Building
- Build package: `uv build`

## Architecture Overview

StrongBus is a type-safe event bus library with three core components:

### Core Components (`src/strongbus/core.py`)
- **Event**: Base class for all events - simple data containers that inherit from Event
- **EventBus**: Central hub managing subscriptions and publishing events
  - Uses weak references for method callbacks (automatic cleanup)
  - Strong references for function callbacks (manual cleanup required)
  - Type-safe subscription system with generics
  - Global subscriptions via `subscribe_global`/`unsubscribe_global`: a callback receives every published event (for cross-cutting concerns like logging)
- **Enrollment**: Base class for objects that need to manage multiple event subscriptions
  - Tracks all subscriptions (including global ones) for easy bulk cleanup with `clear()`
  - Inherits from ABC and provides convenient subscription management

### Key Design Patterns
- **Type Safety**: Callbacks are typed to receive specific event types using generics
- **Memory Management**: Automatic cleanup of dead method references via `weakref.WeakMethod`
- **Event Isolation**: Events don't propagate to parent/child types - exact type matching only (global subscribers receive everything)
- **Subscription Tracking**: Enrollment pattern allows bulk unsubscription

### Project Structure
- `src/strongbus/__init__.py`: Public API exports (EventBus, Event, Enrollment)
- `src/strongbus/core.py`: Core implementation
- `src/strongbus/test_core.py`: Comprehensive test suite
- `src/strongbus/py.typed`: Marker that the package ships type hints

### Dependencies
- Zero runtime dependencies (pure Python)
- Development dependencies (`dev` extra in pyproject.toml): tox, build, pytest-cov, ruff, ty
- Supports Python 3.10+ (as specified in pyproject.toml)

### Testing Strategy
- Tests are written with Python's unittest framework and run via pytest
- Mock objects for testing callbacks
- Tests cover weak reference cleanup, type isolation, global subscriptions, and memory management
- CI (GitHub Actions) runs `tox` against Python 3.10–3.13 and uploads coverage to Codecov
