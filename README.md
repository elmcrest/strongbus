
[![codecov](https://codecov.io/github/elmcrest/strongbus/graph/badge.svg?token=GMSWeOkKQS)](https://codecov.io/github/elmcrest/strongbus)
# StrongBus

A type-safe event bus library for Python that provides reliable publish-subscribe messaging with automatic memory management, full type safety, and global event subscriptions for cross-cutting concerns like logging.

## Features

- **Type Safety**: Full type checking with generics ensures callbacks receive the correct event types
- **Memory Management**: Automatic cleanup of dead references using weak references for methods
- **Subscription Management**: Easy subscription tracking and bulk cleanup via the Enrollment pattern
- **Global Subscriptions**: Subscribe to all events for cross-cutting concerns like logging and monitoring
- **Event Isolation**: Events don't propagate to parent/child types - each event type is handled independently
- **Zero Dependencies**: Pure Python implementation with no external dependencies

## Installation

```bash
pip install strongbus
```

For development (uses [uv](https://docs.astral.sh/uv/)):
```bash
uv sync --extra dev
```

## Quick Start

```python
from dataclasses import dataclass
from strongbus import Event, EventBus, Enrollment

# Define your events
@dataclass(frozen=True)
class UserLoginEvent(Event):
    username: str

# Create subscribers using Enrollment
class NotificationService(Enrollment):
    def __init__(self, event_bus: EventBus):
        super().__init__(event_bus)
        self.subscribe(UserLoginEvent, self.on_user_login)
    
    def on_user_login(self, event: UserLoginEvent) -> None:
        print(f"Welcome {event.username}!")

# Usage
event_bus = EventBus()
service = NotificationService(event_bus)
event_bus.publish(UserLoginEvent(username="Alice"))
# Output: Welcome Alice!

# Cleanup
service.clear()  # Automatically unsubscribes from all events
```

## Core Concepts

### Events

Events are simple data classes that inherit from the `Event` base class:

```python
@dataclass(frozen=True)
class OrderCreatedEvent(Event):
    order_id: str
    customer_id: str
    total: float
```

### EventBus

The central hub for publishing and subscribing to events:

```python
event_bus = EventBus()

# Subscribe to events
event_bus.subscribe(OrderCreatedEvent, handle_order)

# Publish events
event_bus.publish(OrderCreatedEvent(
    order_id="12345",
    customer_id="user123", 
    total=99.99
))
```

Subscriptions have set semantics: a callback is either subscribed to an event type or it isn't. Subscribing the same callback again is a no-op, and `unsubscribe` removes it entirely. Callbacks are matched by identity (bound methods by the instance and function they wrap), never by `==`, so two distinct handlers that happen to compare equal are still two subscriptions.

Identity matching means subscribers can't be kept in a hash-based set, so
`subscribe` and `unsubscribe` scan the event type's subscriber list linearly.
With the typical handful of subscribers per event type this is negligible —
but if you register thousands of subscribers for a single event type, expect
those operations (not `publish`, which is linear in subscriber count anyway)
to scale accordingly.

Set semantics apply at the bus level, not per Enrollment: if a callback is
already subscribed to an event type — directly on the bus or through another
Enrollment — subscribing it again through an Enrollment is a no-op that does
not take ownership. A subscription is removed only by whoever created it: an
Enrollment's `unsubscribe`/`clear` only touch subscriptions made through that
Enrollment (`EventBus.subscribe` returns `True` when it actually added the
subscription). Give each Enrollment its own callback (typically its own bound
methods) to keep their lifecycles independent.

### Enrollment

A base class that simplifies subscription management. See [Wiring the Event Bus in Your Application](#wiring-the-event-bus-in-your-application) below for guidance on creating the bus and passing it into your services in a real application:

```python
class OrderProcessor(Enrollment):
    def __init__(self, event_bus: EventBus):
        super().__init__(event_bus)
        self.subscribe(OrderCreatedEvent, self.process_order)
        self.subscribe(PaymentReceivedEvent, self.confirm_payment)
    
    def process_order(self, event: OrderCreatedEvent) -> None:
        # Handle order processing
        pass
    
    def confirm_payment(self, event: PaymentReceivedEvent) -> None:
        # Handle payment confirmation
        pass
```

## Wiring the Event Bus in Your Application

StrongBus does not provide (or assume) a global or singleton bus instance. The recommended pattern is to create one or more `EventBus` instances at your composition root or application factory and pass the instance explicitly to the objects that need it.

This approach has several advantages:

- Dependencies are visible in constructors
- Testing is straightforward: create a fresh `EventBus()` per test for complete isolation (this is exactly what the library's own test suite does)
- Multiple independent buses are easy when you need them (e.g. separate business-domain events from system/audit events, or isolated buses per subsystem or tenant)
- It works naturally with `Enrollment`, whose constructor takes the bus

### Composition root / startup wiring

Create the bus once during application startup and wire your services there:

```python
from strongbus import EventBus
from .services import NotificationService, AuditLogger, OrderProcessor

def create_app():
    """Typical composition root or application factory."""
    event_bus = EventBus()

    # Cross-cutting concerns (frequently using global subscriptions) are often wired first
    audit_logger = AuditLogger(event_bus)

    # Domain services
    notifications = NotificationService(event_bus)
    processor = OrderProcessor(event_bus)

    # Return whatever container or object your app uses
    return {
        "bus": event_bus,
        "services": {
            "audit": audit_logger,
            "notifications": notifications,
            "processor": processor,
        },
    }
```

Call this once when your process starts. On shutdown, call `.clear()` on any long-lived `Enrollment` instances if you want deterministic unsubscription.

### Frameworks and existing DI containers

If you use a web framework or a dependency-injection library:

- Store the bus on your application object (`app.bus`, `app.state.event_bus`, etc.)
- Register the bus instance in your DI container and inject it into `Enrollment` subclass constructors at startup time
- Create long-lived subscriber services at application startup, not per-request

You can also let a high-level coordinator or "App" class inherit from `Enrollment` directly:

```python
class MyApplication(Enrollment):
    def __init__(self):
        super().__init__(EventBus())
        self.subscribe(OrderCreatedEvent, self.on_order_created)
        # ...

    def on_order_created(self, event: OrderCreatedEvent) -> None:
        ...
```

Once wired, the coordinator can publish via `self.publish(SomeEvent(...))` as well as `clear()` itself on shutdown.

### Short-lived subscribers

For objects that only need to listen for a limited time (a request handler, a background job, etc.), instantiate an `Enrollment`, subscribe what you need, do the work, and call `clear()` when finished.

### Testing

Create a fresh bus for every test. This gives you perfect isolation with no shared global state:

```python
def test_order_processing():
    bus = EventBus()
    processor = OrderProcessor(bus)

    bus.publish(UserLoginEvent(username="test"))
    # assertions...

    # Explicit clear is usually unnecessary in tests when using bound methods,
    # but harmless and good for symmetry with production shutdown code.
    processor.clear()
```

The large example near the end of this document follows the same explicit-wiring style inside its `if __name__ == "__main__":` block.

## Global Event Subscriptions

StrongBus supports global event subscriptions for services that need to receive all events, such as logging or monitoring services:

```python
class LoggerService(Enrollment):
    """Example service that logs all events using global subscription."""
    
    def __init__(self, event_bus: EventBus):
        super().__init__(event_bus)
        self.subscribe_global(self._log_event)
    
    def _log_event(self, event: Event) -> None:
        """Log any event that occurs."""
        event_type = type(event).__name__
        print(f"[LOG] {event_type}: {event}")

# Usage
event_bus = EventBus()
logger = LoggerService(event_bus)

# Create other services
notification_service = NotificationService(event_bus)

# All events will be logged automatically
event_bus.publish(UserLoginEvent(username="Alice"))
# Output: 
# [LOG] UserLoginEvent: UserLoginEvent(username='Alice')
# Welcome Alice!

event_bus.publish(OrderCreatedEvent(order_id="123", customer_id="user1", total=99.99))
# Output:
# [LOG] OrderCreatedEvent: OrderCreatedEvent(order_id='123', customer_id='user1', total=99.99)
```

Global subscriptions can be managed just like regular subscriptions:

```python
# Unsubscribe from global events
logger.unsubscribe_global(logger._log_event)

# Or clear all subscriptions (including global ones)
logger.clear()
```

## Memory Management

StrongBus automatically manages memory to prevent leaks:

- **Method callbacks** use weak references and are automatically cleaned up when the object is garbage collected
- **Function callbacks** use strong references and persist until explicitly unsubscribed
- **Enrollment pattern** provides easy bulk cleanup with `clear()`; its tracking
  follows the same rule (bound methods are tracked weakly), so an Enrollment
  never keeps a subscriber object alive just by tracking it

> **Warning:** Only bound methods are held weakly. Lambdas, `functools.partial`
> objects, and callable instances count as functions and are held strongly — a
> lambda that captures `self` keeps that object alive until you unsubscribe it.
> Subscribe bound methods when you want automatic cleanup.

## Sync only (for now)

Callbacks are called synchronously by `publish()` and are never awaited, so
`async def` callbacks are not supported: subscribing a coroutine function
raises `TypeError` at subscribe time (instead of silently producing an
unawaited coroutine on every publish). To hand events off to asyncio code,
subscribe a synchronous callback that schedules the work, e.g. via
`asyncio.get_running_loop().create_task(...)` or
`asyncio.run_coroutine_threadsafe(...)`.

## Error Handling

A subscriber that raises does not affect delivery to other subscribers: every
subscriber (including global ones) is notified first, and only then does the
publisher see the failure.

- If exactly one callback raised, its original exception is re-raised
  unchanged, so existing `except SomeError:` handling around `publish()` keeps
  working.
- If several callbacks raised, a `strongbus.PublishError` (a subclass of the
  built-in `ExceptionGroup`) is raised containing all of them — it works with
  `except*` and exposes the individual exceptions via `.exceptions`.

```python
from strongbus import PublishError

try:
    event_bus.publish(OrderCreatedEvent(order_id="1", customer_id="u1", total=9.99))
except PublishError as group:
    for exc in group.exceptions:
        log.error("subscriber failed", exc_info=exc)
```

## Thread Safety

`EventBus` and `Enrollment` are thread-safe: subscribing, unsubscribing, and
publishing may happen concurrently from any number of threads.

Callbacks are invoked on the thread that calls `publish()`, outside the bus's
internal lock. This means:

- A callback may freely subscribe, unsubscribe, or publish further events without deadlocking.
- If events are published from multiple threads, your callbacks must be thread-safe themselves.
- A subscription added while a publish is in flight only receives subsequent events.
- `unsubscribe()` is not a delivery barrier: a publish already in flight on
  another thread iterates a snapshot of the subscriber list, so the callback
  may still be invoked once after `unsubscribe()` returns.

## Testing

### Using tox (recommended)

Install tox with uv support:
```bash
uv tool install tox --with tox-uv
```

Run all tests across multiple Python versions:
```bash
tox
```

### Manual testing

Run the test suite directly:
```bash
uv run --extra dev pytest
```

## Slightly larger example
```python
from dataclasses import dataclass

from strongbus import Event, EventBus, Enrollment


@dataclass(frozen=True)
class UserLoginEvent(Event):
    username: str


@dataclass(frozen=True)
class UserLogoutEvent(Event):
    username: str


@dataclass(frozen=True)
class DataUpdatedEvent(Event):
    data_id: str
    new_value: str


@dataclass(frozen=True)
class TestEvent(Event):
    message: str


class PackageManager(Enrollment):
    def __init__(self, event_bus: EventBus):
        super().__init__(event_bus)
        # Type-safe subscription - callback must accept UserLoginEvent
        self.subscribe(UserLoginEvent, self.on_user_login)
        self.subscribe(DataUpdatedEvent, self.on_data_updated)

    def on_user_login(self, event: UserLoginEvent) -> None:
        # Can access event.username with full type safety
        print(f"PackageManager: User {event.username} logged in")

    def on_data_updated(self, event: DataUpdatedEvent) -> None:
        print(f"PackageManager: Data {event.data_id} updated to {event.new_value}")


class ContainerManager(Enrollment):
    def __init__(self, event_bus: EventBus):
        super().__init__(event_bus)
        self.subscribe(UserLoginEvent, self.on_user_login)
        self.subscribe(UserLogoutEvent, self.on_user_logout)

    def on_user_login(self, event: UserLoginEvent) -> None:
        print(f"ContainerManager: User {event.username} logged in")

    def on_user_logout(self, event: UserLogoutEvent) -> None:
        print(f"ContainerManager: User {event.username} logged out")


if __name__ == "__main__":
    # Usage
    event_bus = EventBus()
    manager0 = PackageManager(event_bus)
    manager1 = ContainerManager(event_bus)

    # Publish events - type-safe with proper event objects
    event_bus.publish(UserLoginEvent(username="Alice"))
    # Output:
    # PackageManager: User Alice logged in
    # ContainerManager: User Alice logged in

    event_bus.publish(UserLogoutEvent(username="Alice"))
    # Output:
    # ContainerManager: User Alice logged out

    event_bus.publish(DataUpdatedEvent(data_id="123", new_value="new data"))
    # Output:
    # PackageManager: Data 123 updated to new data

    # List all available event types
    print("\nAvailable event types:")
    for event_class in Event.__subclasses__():
        print(f"  - {event_class.__name__}")

    # Cleanup
    manager0.clear()
    manager1.clear()

```

## License

[MIT](LICENSE)
