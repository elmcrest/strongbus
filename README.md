
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

For development:
```bash
pip install -e .
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

### Enrollment

A base class that simplifies subscription management:

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
- **Enrollment pattern** provides easy bulk cleanup with `clear()`

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
python -m unittest src/strongbus/tests.py
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