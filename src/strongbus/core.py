import inspect
import weakref
from abc import ABC
from typing import Callable, Dict, List, Type, TypeVar, Union


class Event:
    """Base class for all events. Subclass for specific types."""

    pass


SpecificEvent = TypeVar("SpecificEvent", bound=Event)

EventHandler = Callable[[Event], None]
SubscriberType = Union[EventHandler, weakref.WeakMethod[EventHandler]]


class EventBus:
    def __init__(self):
        self._subscribers: Dict[Type[Event], List[SubscriberType]] = {}
        self._global_subscribers: List[SubscriberType] = []

    def subscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Subscribe to a specific event type with a type-safe callback."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        if inspect.ismethod(callback):
            weak_callback = weakref.WeakMethod(callback)  # type: ignore[arg-type]
        else:
            weak_callback = callback  # type: ignore[assignment]

        self._subscribers[event_type].append(weak_callback)

    def subscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Subscribe to all events with a callback that receives any event."""
        if inspect.ismethod(callback):
            global_weak_callback = weakref.WeakMethod(callback)  # type: ignore[arg-type]
        else:
            global_weak_callback = callback  # type: ignore[assignment]

        self._global_subscribers.append(global_weak_callback)

    def unsubscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Unsubscribe a callback from a specific event type."""
        if event_type in self._subscribers:
            to_remove: List[SubscriberType] = []
            for weak_cb in self._subscribers[event_type]:
                if isinstance(weak_cb, weakref.WeakMethod):
                    cb: Callable[[Event], None] | None = weak_cb()
                    if cb is not None and cb == callback:
                        to_remove.append(weak_cb)
                else:
                    if weak_cb == callback:
                        to_remove.append(weak_cb)
            for r in to_remove:
                self._subscribers[event_type].remove(r)

    def unsubscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Unsubscribe a global callback from all events."""
        to_remove: List[SubscriberType] = []
        for weak_cb in self._global_subscribers:
            if isinstance(weak_cb, weakref.WeakMethod):
                cb: Callable[[Event], None] | None = weak_cb()
                if cb is not None and cb == callback:
                    to_remove.append(weak_cb)
            else:
                if weak_cb == callback:
                    to_remove.append(weak_cb)
        for r in to_remove:
            self._global_subscribers.remove(r)

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type and all global subscribers."""
        event_type = type(event)
        
        # Notify specific event type subscribers
        if event_type in self._subscribers:
            subscribers = self._subscribers[event_type][
                :
            ]  # Copy to avoid modification during iteration
            for weak_cb in subscribers:
                if isinstance(weak_cb, weakref.WeakMethod):
                    cb: Callable[[Event], None] | None = weak_cb()
                    if cb is not None:
                        cb(event)
                    else:
                        self._subscribers[event_type].remove(weak_cb)
                else:
                    weak_cb(event)
        
        # Notify global subscribers
        global_subscribers = self._global_subscribers[:]  # Copy to avoid modification during iteration
        for weak_cb in global_subscribers:
            if isinstance(weak_cb, weakref.WeakMethod):
                global_cb: Callable[[Event], None] | None = weak_cb()
                if global_cb is not None:
                    global_cb(event)
                else:
                    self._global_subscribers.remove(weak_cb)
            else:
                weak_cb(event)


class Enrollment(ABC):
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._subscriptions: Dict[Type[Event], List[Callable[[Event], None]]] = {}
        self._global_subscriptions: List[Callable[[Event], None]] = []

    def subscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Subscribe to an event type with automatic tracking."""
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(callback)  # type: ignore
        self._event_bus.subscribe(event_type, callback)

    def subscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Subscribe to all events with automatic tracking."""
        self._global_subscriptions.append(callback)
        self._event_bus.subscribe_global(callback)

    def unsubscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._subscriptions:
            self._subscriptions[event_type] = [
                cb for cb in self._subscriptions[event_type] if cb != callback
            ]
            self._event_bus.unsubscribe(event_type, callback)
            if not self._subscriptions[event_type]:
                del self._subscriptions[event_type]

    def unsubscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Unsubscribe from all events."""
        self._global_subscriptions = [cb for cb in self._global_subscriptions if cb != callback]
        self._event_bus.unsubscribe_global(callback)

    def publish(self, event: Event) -> None:
        """Publish an event through the event bus."""
        self._event_bus.publish(event)

    def clear(self) -> None:
        """Unsubscribe from all events."""
        for event_type, callbacks in list(self._subscriptions.items()):
            for callback in callbacks:
                self._event_bus.unsubscribe(event_type, callback)
        self._subscriptions.clear()
        
        for callback in self._global_subscriptions:
            self._event_bus.unsubscribe_global(callback)
        self._global_subscriptions.clear()
