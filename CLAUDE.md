# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project is managed with `uv`. The dev extra includes tox with the tox-uv plugin, so `uv run --extra dev tox` works; a global install via `uv tool install tox --with tox-uv` works too.

### Testing
- Run all tests: `uv run --extra dev pytest`
- With coverage (as CI does): `uv run --extra dev pytest --cov --cov-branch --cov-report=xml`
- Across Python 3.11–3.14: `tox`

### Linting and Type Checking
- Lint check (no changes): `tox -e lint`
- Lint with auto-fix: `tox -e fix`
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
  - Tracking mirrors the bus's reference policy: bound methods via `WeakMethod`, functions strongly — an Enrollment never keeps a subscriber object alive just by tracking it
  - Provides convenient subscription management as a plain base class

### Key Design Patterns
- **Type Safety**: Callbacks are typed to receive specific event types using generics
- **Memory Management**: Automatic cleanup of dead method references via `weakref.WeakMethod`; death callbacks queue dead entries in `_pending_removals`, purged on the next bus operation under the lock. Emptied event-type keys are dropped so they don't pin (dynamically created) event classes
- **Event Isolation**: Events don't propagate to parent/child types - exact type matching only (global subscribers receive everything)
- **Subscription Tracking**: Enrollment pattern allows bulk unsubscription
- **Set Semantics**: Subscribing an already-subscribed callback is a no-op; a callback is either subscribed or not. Callbacks are matched by identity (bound methods by their `(__self__, __func__)` pair), never by `==`, so a custom `__eq__` can't deduplicate or unsubscribe a different handler
- **Thread Safety**: All operations are guarded by an RLock; publish snapshots subscriber lists under the lock but invokes callbacks outside it (so callbacks can re-enter the bus). WeakMethod death callbacks may fire at any moment on any thread, so they only append to `_pending_removals` and never touch the lock
- **Error Isolation**: A raising callback doesn't block delivery to other subscribers; publish notifies everyone first, then re-raises a single failure unchanged or raises `PublishError` (an `ExceptionGroup` subclass) for multiple failures

### Project Structure
- `src/strongbus/__init__.py`: Public API exports (EventBus, Event, Enrollment, PublishError)
- `src/strongbus/core.py`: Core implementation
- `src/strongbus/py.typed`: Marker that the package ships type hints
- `tests/test_core.py`: Core test suite
- `tests/test_threading.py`: Concurrency tests

### Dependencies
- Zero runtime dependencies (pure Python)
- Development dependencies (`dev` extra in pyproject.toml): tox, build, pytest-cov, ruff, ty
- Supports Python 3.11+ (as specified in pyproject.toml)

### Testing Strategy
- Tests are written with Python's unittest framework and run via pytest
- Mock objects for testing callbacks
- Tests cover weak reference cleanup, type isolation, global subscriptions, memory management, and thread safety (concurrent publish/subscribe churn, GC of subscribers during publishing)
- CI (GitHub Actions) runs `tox` against Python 3.11–3.14, enforces `tox -e lint,ty`, and uploads coverage to Codecov
