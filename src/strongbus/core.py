import inspect
import threading
import weakref
from abc import ABC
from typing import Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union


class Event:
    """Base class for all events. Subclass for specific types."""

    pass


SpecificEvent = TypeVar("SpecificEvent", bound=Event)

EventHandler = Callable[[Event], None]
SubscriberType = Union[EventHandler, weakref.WeakMethod[EventHandler]]


class EventBus:
    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: Dict[Type[Event], List[SubscriberType]] = {}
        self._global_subscribers: List[SubscriberType] = []
        # Dead WeakMethods queued by their death callbacks. A death callback
        # can fire whenever the gc runs - on any thread, even while this
        # thread holds the lock - so it must only append here (atomic);
        # actual removal happens in _flush_pending under the lock.
        self._pending_removals: List[
            Tuple[Optional[Type[Event]], "weakref.WeakMethod[EventHandler]"]
        ] = []

    def _flush_pending(self) -> None:
        """Remove entries of dead methods. Must be called with the lock held."""
        while self._pending_removals:
            event_type, ref = self._pending_removals.pop()
            target = (
                self._global_subscribers
                if event_type is None
                else self._subscribers.get(event_type, [])
            )
            try:
                target.remove(ref)
            except ValueError:
                pass  # already removed by unsubscribe or an earlier flush

    @staticmethod
    def _is_subscribed(
        subscribers: List[SubscriberType], callback: Callable[..., None]
    ) -> bool:
        """Check whether a live entry for this callback already exists."""
        for weak_cb in subscribers:
            if isinstance(weak_cb, weakref.WeakMethod):
                if weak_cb() == callback:
                    return True
            elif weak_cb == callback:
                return True
        return False

    def subscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Subscribe to a specific event type with a type-safe callback.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op.
        """
        with self._lock:
            self._flush_pending()
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            if self._is_subscribed(self._subscribers[event_type], callback):
                return

            if inspect.ismethod(callback):
                weak_callback = weakref.WeakMethod(
                    callback,  # type: ignore[arg-type]
                    lambda ref: self._pending_removals.append((event_type, ref)),
                )
            else:
                weak_callback = callback  # type: ignore[assignment]

            self._subscribers[event_type].append(weak_callback)

    def subscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Subscribe to all events with a callback that receives any event.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op.
        """
        with self._lock:
            self._flush_pending()
            if self._is_subscribed(self._global_subscribers, callback):
                return

            if inspect.ismethod(callback):
                global_weak_callback = weakref.WeakMethod(
                    callback,  # type: ignore[arg-type]
                    lambda ref: self._pending_removals.append((None, ref)),
                )
            else:
                global_weak_callback = callback  # type: ignore[assignment]

            self._global_subscribers.append(global_weak_callback)

    def unsubscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Unsubscribe a callback from a specific event type."""
        with self._lock:
            self._flush_pending()
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
        with self._lock:
            self._flush_pending()
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
        """Publish an event to all subscribers of its type and all global subscribers.

        Callbacks run on the publishing thread, outside the internal lock, so
        they may freely subscribe, unsubscribe, or publish. A subscription
        added while a publish is in flight only receives subsequent events.
        """
        if not isinstance(event, Event):
            raise TypeError(
                "strongbus only handles events of type Event (or subclasses)"
            )
        event_type = type(event)

        with self._lock:
            self._flush_pending()
            subscribers = list(self._subscribers.get(event_type, ()))
            global_subscribers = list(self._global_subscribers)

        # Notify specific event type subscribers
        for weak_cb in subscribers:
            if isinstance(weak_cb, weakref.WeakMethod):
                cb: Callable[[Event], None] | None = weak_cb()
                if cb is not None:
                    cb(event)
                # a dead ref was queued for removal by its death callback
            else:
                weak_cb(event)

        # Notify global subscribers
        for weak_cb in global_subscribers:
            if isinstance(weak_cb, weakref.WeakMethod):
                global_cb: Callable[[Event], None] | None = weak_cb()
                if global_cb is not None:
                    global_cb(event)
            else:
                weak_cb(event)


class Enrollment(ABC):
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._subscriptions: Dict[Type[Event], List[Callable[[Event], None]]] = {}
        self._global_subscriptions: List[Callable[[Event], None]] = []

    def subscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Subscribe to an event type with automatic tracking.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op.
        """
        with self._lock:
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            if callback in self._subscriptions[event_type]:
                return
            self._subscriptions[event_type].append(callback)  # type: ignore
            self._event_bus.subscribe(event_type, callback)

    def subscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Subscribe to all events with automatic tracking.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op.
        """
        with self._lock:
            if callback in self._global_subscriptions:
                return
            self._global_subscriptions.append(callback)
            self._event_bus.subscribe_global(callback)

    def unsubscribe(
        self, event_type: Type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscriptions:
                self._subscriptions[event_type] = [
                    cb for cb in self._subscriptions[event_type] if cb != callback
                ]
                self._event_bus.unsubscribe(event_type, callback)
                if not self._subscriptions[event_type]:
                    del self._subscriptions[event_type]

    def unsubscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Unsubscribe from all events."""
        with self._lock:
            self._global_subscriptions = [
                cb for cb in self._global_subscriptions if cb != callback
            ]
            self._event_bus.unsubscribe_global(callback)

    def publish(self, event: Event) -> None:
        """Publish an event through the event bus."""
        self._event_bus.publish(event)

    def clear(self) -> None:
        """Unsubscribe from all events."""
        with self._lock:
            for event_type, callbacks in list(self._subscriptions.items()):
                for callback in callbacks:
                    self._event_bus.unsubscribe(event_type, callback)
            self._subscriptions.clear()

            for callback in self._global_subscriptions:
                self._event_bus.unsubscribe_global(callback)
            self._global_subscriptions.clear()
