# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Testing
```bash
python -m unittest src/strongbus/tests.py
```

### Build and Package
```bash
python -m build
```

### Install in Development Mode
```bash
pip install -e .
```

## Architecture

StrongBus is a type-safe event bus library for Python with these core components:

### Core Classes (`src/strongbus/core.py`)
- **Event**: Base class for all events. All event types must inherit from this class.
- **EventBus**: Central event dispatcher that manages subscriptions and publishing
  - Uses weak references for method callbacks to prevent memory leaks
  - Strong references for function callbacks
  - Type-safe subscription with generic type constraints
- **Enrollment**: Abstract base class that provides subscription management with automatic cleanup
  - Tracks all subscriptions for easy bulk unsubscription via `clear()`
  - Delegates to EventBus for actual event handling

### Key Design Patterns
- **Type Safety**: Uses generics (`SpecificEvent = TypeVar("SpecificEvent", bound=Event)`) to ensure callbacks receive the correct event type
- **Memory Management**: Automatic cleanup of dead method references using `weakref.WeakMethod`
- **Inheritance Isolation**: Events don't propagate to parent/child types - each event type is handled independently
- **Subscription Tracking**: Enrollment pattern allows components to manage their own subscriptions lifecycle

### Event Flow
1. Create event classes by inheriting from `Event` (typically as frozen dataclasses)
2. Components inherit from `Enrollment` and subscribe to specific event types
3. Events are published through EventBus and delivered only to exact type matches
4. Cleanup handled automatically via weak references or explicit `clear()` calls

### Testing
Comprehensive test suite in `src/strongbus/tests.py` covers:
- Basic subscription/publishing
- Multiple subscribers
- Type isolation
- Memory management (weak references)
- Subscription cleanup