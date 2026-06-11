import inspect
import threading
import weakref
from collections.abc import Callable, Sequence
from typing import TypeVar


class Event:
    """Base class for all events. Subclass for specific types."""

    pass


class PublishError(ExceptionGroup):
    """Raised by publish when more than one subscriber raises.

    Delivery always completes to every subscriber before this is raised.
    If exactly one subscriber raises, its original exception is re-raised
    instead of being wrapped.
    """

    def derive(self, excs: Sequence[Exception]) -> "PublishError":
        return PublishError(self.message, list(excs))


SpecificEvent = TypeVar("SpecificEvent", bound=Event)

EventHandler = Callable[[Event], None]
SubscriberType = EventHandler | weakref.WeakMethod[EventHandler]


def _same_callback(a: Callable[..., None], b: Callable[..., None]) -> bool:
    """Whether two callables denote the same subscriber.

    Bound methods are recreated on every attribute access, so they are
    matched by the identity of their (__self__, __func__) pair; everything
    else is matched by plain identity. Equality is deliberately not used:
    a callable with custom __eq__ could otherwise silently match - and be
    deduplicated or unsubscribed as - a different handler.
    """
    if inspect.ismethod(a) and inspect.ismethod(b):
        return a.__self__ is b.__self__ and a.__func__ is b.__func__
    return a is b


def _validate_event_type(event_type: object) -> None:
    if not (isinstance(event_type, type) and issubclass(event_type, Event)):
        raise TypeError(f"event_type must be an Event subclass, got {event_type!r}")


def _validate_callback(callback: Callable[..., object]) -> None:
    # publish() calls subscribers synchronously and never awaits, so an
    # async callback would only ever produce an unawaited coroutine -
    # reject it here, where the mistake is made, instead of failing
    # silently on every publish.
    if inspect.iscoroutinefunction(callback):
        raise TypeError(
            f"async callbacks are not supported: {callback!r} would never be "
            "awaited by publish(). Subscribe a synchronous callback instead."
        )


def _is_subscribed(
    subscribers: list[SubscriberType], callback: Callable[..., None]
) -> bool:
    """Check whether a live entry for this callback already exists."""
    for weak_cb in subscribers:
        if isinstance(weak_cb, weakref.WeakMethod):
            cb = weak_cb()
            if cb is not None and _same_callback(cb, callback):
                return True
        elif _same_callback(weak_cb, callback):
            return True
    return False


class EventBus:
    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: dict[type[Event], list[SubscriberType]] = {}
        self._global_subscribers: list[SubscriberType] = []
        # Dead WeakMethods queued by their death callbacks. A death callback
        # can fire whenever the gc runs - on any thread, even while this
        # thread holds the lock - so it must only append here (atomic);
        # actual removal happens in _flush_pending under the lock.
        self._pending_removals: list[
            tuple[type[Event] | None, "weakref.WeakMethod[EventHandler]"]
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
            # drop an emptied key: it would otherwise keep the event class
            # itself alive, a leak for dynamically created event types
            if event_type is not None and not target:
                self._subscribers.pop(event_type, None)

    def subscribe(
        self, event_type: type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> bool:
        """Subscribe to a specific event type with a type-safe callback.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op. Returns True if the callback was newly
        subscribed, False if it was already subscribed.

        Raises TypeError if event_type is not an Event subclass, or if
        callback is a coroutine function (publish never awaits).
        """
        _validate_event_type(event_type)
        _validate_callback(callback)
        with self._lock:
            self._flush_pending()
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            if _is_subscribed(self._subscribers[event_type], callback):
                return False

            if inspect.ismethod(callback):
                weak_callback = weakref.WeakMethod(
                    callback,  # type: ignore[arg-type]
                    lambda ref: self._pending_removals.append((event_type, ref)),
                )
            else:
                weak_callback = callback  # type: ignore[assignment]

            self._subscribers[event_type].append(weak_callback)
            return True

    def subscribe_global(self, callback: Callable[[Event], None]) -> bool:
        """Subscribe to all events with a callback that receives any event.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op. Returns True if the callback was newly
        subscribed, False if it was already subscribed.

        Raises TypeError if callback is a coroutine function (publish
        never awaits).
        """
        _validate_callback(callback)
        with self._lock:
            self._flush_pending()
            if _is_subscribed(self._global_subscribers, callback):
                return False

            if inspect.ismethod(callback):
                global_weak_callback = weakref.WeakMethod(
                    callback,  # type: ignore[arg-type]
                    lambda ref: self._pending_removals.append((None, ref)),
                )
            else:
                global_weak_callback = callback  # type: ignore[assignment]

            self._global_subscribers.append(global_weak_callback)
            return True

    def unsubscribe(
        self, event_type: type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Unsubscribe a callback from a specific event type.

        Not a delivery barrier: a publish already in flight on another
        thread iterates a snapshot of the subscriber list, so the callback
        may still be invoked once after this returns.

        Raises TypeError if event_type is not an Event subclass.
        """
        _validate_event_type(event_type)
        with self._lock:
            self._flush_pending()
            if event_type in self._subscribers:
                to_remove: list[SubscriberType] = []
                for weak_cb in self._subscribers[event_type]:
                    if isinstance(weak_cb, weakref.WeakMethod):
                        cb: Callable[[Event], None] | None = weak_cb()
                        if cb is not None and _same_callback(cb, callback):
                            to_remove.append(weak_cb)
                    else:
                        if _same_callback(weak_cb, callback):
                            to_remove.append(weak_cb)
                for r in to_remove:
                    self._subscribers[event_type].remove(r)
                if not self._subscribers[event_type]:
                    del self._subscribers[event_type]

    def unsubscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Unsubscribe a global callback from all events.

        Not a delivery barrier: a publish already in flight on another
        thread iterates a snapshot of the subscriber list, so the callback
        may still be invoked once after this returns.
        """
        with self._lock:
            self._flush_pending()
            to_remove: list[SubscriberType] = []
            for weak_cb in self._global_subscribers:
                if isinstance(weak_cb, weakref.WeakMethod):
                    cb: Callable[[Event], None] | None = weak_cb()
                    if cb is not None and _same_callback(cb, callback):
                        to_remove.append(weak_cb)
                else:
                    if _same_callback(weak_cb, callback):
                        to_remove.append(weak_cb)
            for r in to_remove:
                self._global_subscribers.remove(r)

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type and all global subscribers.

        Callbacks run on the publishing thread, outside the internal lock, so
        they may freely subscribe, unsubscribe, or publish. A subscription
        added while a publish is in flight only receives subsequent events;
        one removed while a publish is in flight may still receive that event.

        A subscriber that raises does not affect delivery to the others:
        every subscriber is notified first, then the publisher sees the
        original exception (one failure) or a PublishError grouping them
        (several failures).
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

        errors: list[Exception] = []
        for weak_cb in (*subscribers, *global_subscribers):
            if isinstance(weak_cb, weakref.WeakMethod):
                cb: Callable[[Event], None] | None = weak_cb()
                if cb is None:
                    # a dead ref was queued for removal by its death callback
                    continue
            else:
                cb = weak_cb
            try:
                cb(event)
            except Exception as exc:
                errors.append(exc)

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise PublishError(
                f"{len(errors)} subscribers raised while handling "
                f"{event_type.__name__}",
                errors,
            )


class Enrollment:
    """Tracks an object's subscriptions for bulk cleanup with clear().

    Tracking follows the bus's reference policy: bound methods are tracked
    weakly, everything else strongly. An enrollment therefore never keeps a
    subscriber object alive just by tracking it.
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._subscriptions: dict[type[Event], list[SubscriberType]] = {}
        self._global_subscriptions: list[SubscriberType] = []

    @staticmethod
    def _wrap(callback: Callable[..., None]) -> SubscriberType:
        if inspect.ismethod(callback):
            return weakref.WeakMethod(callback)  # type: ignore[arg-type]
        return callback

    @staticmethod
    def _live(entry: SubscriberType) -> EventHandler | None:
        """Dereference a tracked entry; None if its owner has died."""
        if isinstance(entry, weakref.WeakMethod):
            return entry()
        return entry

    def subscribe(
        self, event_type: type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Subscribe to an event type with automatic tracking.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op. The set lives on the bus, not per enrollment:
        if the same callback is already subscribed to the same event type -
        directly on the bus or through another enrollment - this is a no-op
        and ownership stays with the original subscriber; this enrollment
        will not track or remove that subscription.

        Raises TypeError if event_type is not an Event subclass, or if
        callback is a coroutine function (publish never awaits).
        """
        with self._lock:
            if _is_subscribed(self._subscriptions.get(event_type, []), callback):
                return
            # subscribe first so a rejected event_type or callback is never
            # tracked;
            # only track what the bus actually added, so clear() never
            # removes a subscription this enrollment did not create
            if not self._event_bus.subscribe(event_type, callback):
                return
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            self._subscriptions[event_type].append(self._wrap(callback))

    def subscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Subscribe to all events with automatic tracking.

        Subscriptions have set semantics: subscribing an already-subscribed
        callback is a no-op. If the callback is already subscribed globally
        elsewhere, ownership stays with the original subscriber; this
        enrollment will not track or remove that subscription.

        Raises TypeError if callback is a coroutine function (publish
        never awaits).
        """
        with self._lock:
            if _is_subscribed(self._global_subscriptions, callback):
                return
            if not self._event_bus.subscribe_global(callback):
                return
            self._global_subscriptions.append(self._wrap(callback))

    @staticmethod
    def _without(
        entries: list[SubscriberType], callback: Callable[..., None]
    ) -> tuple[list[SubscriberType], bool]:
        """Copy entries without the matching callback, pruning dead ones.

        Returns the new list and whether a live matching entry was dropped.
        """
        kept: list[SubscriberType] = []
        dropped = False
        for entry in entries:
            cb = Enrollment._live(entry)
            if cb is None:
                continue
            if _same_callback(cb, callback):
                dropped = True
                continue
            kept.append(entry)
        return kept, dropped

    def unsubscribe(
        self, event_type: type[SpecificEvent], callback: Callable[[SpecificEvent], None]
    ) -> None:
        """Unsubscribe from an event type.

        Only removes subscriptions made through this enrollment: if the
        callback was subscribed on the bus by someone else, the bus
        subscription is left untouched.

        Raises TypeError if event_type is not an Event subclass.
        """
        _validate_event_type(event_type)
        with self._lock:
            if event_type not in self._subscriptions:
                return
            kept, dropped = self._without(self._subscriptions[event_type], callback)
            if kept:
                self._subscriptions[event_type] = kept
            else:
                del self._subscriptions[event_type]
            if dropped:
                self._event_bus.unsubscribe(event_type, callback)

    def unsubscribe_global(self, callback: Callable[[Event], None]) -> None:
        """Unsubscribe from all events.

        Only removes subscriptions made through this enrollment: if the
        callback was subscribed on the bus by someone else, the bus
        subscription is left untouched.
        """
        with self._lock:
            kept, dropped = self._without(self._global_subscriptions, callback)
            self._global_subscriptions = kept
            if dropped:
                self._event_bus.unsubscribe_global(callback)

    def publish(self, event: Event) -> None:
        """Publish an event through the event bus."""
        self._event_bus.publish(event)

    def clear(self) -> None:
        """Unsubscribe from all events."""
        with self._lock:
            for event_type, entries in list(self._subscriptions.items()):
                for entry in entries:
                    cb = self._live(entry)
                    if cb is not None:  # dead refs were already purged by the bus
                        self._event_bus.unsubscribe(event_type, cb)
            self._subscriptions.clear()

            for entry in self._global_subscriptions:
                cb = self._live(entry)
                if cb is not None:
                    self._event_bus.unsubscribe_global(cb)
            self._global_subscriptions.clear()
