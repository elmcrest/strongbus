import gc
import unittest
from dataclasses import dataclass
from unittest.mock import Mock

from strongbus import Enrollment, Event, EventBus


@dataclass(frozen=True)
class MyEvent(Event):
    value: str


@dataclass(frozen=True)
class AnotherEvent(Event):
    number: int


@dataclass(frozen=True)
class SubEvent(MyEvent):
    pass


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_subscribe_and_publish(self):
        callback = Mock()
        self.bus.subscribe(MyEvent, callback)
        event = MyEvent("test")
        self.bus.publish(event)
        callback.assert_called_once_with(event)

    def test_no_subscribers(self):
        event = MyEvent("test")
        # Should not raise any error
        self.bus.publish(event)

    def test_multiple_subscribers(self):
        callback1 = Mock()
        callback2 = Mock()
        self.bus.subscribe(MyEvent, callback1)
        self.bus.subscribe(MyEvent, callback2)
        event = MyEvent("test")
        self.bus.publish(event)
        callback1.assert_called_once_with(event)
        callback2.assert_called_once_with(event)

    def test_different_event_types(self):
        callback_my = Mock()
        callback_another = Mock()
        self.bus.subscribe(MyEvent, callback_my)
        self.bus.subscribe(AnotherEvent, callback_another)
        event_my = MyEvent("test")
        event_another = AnotherEvent(42)
        self.bus.publish(event_my)
        self.bus.publish(event_another)
        callback_my.assert_called_once_with(event_my)
        callback_another.assert_called_once_with(event_another)

    def test_unsubscribe(self):
        callback = Mock()
        self.bus.subscribe(MyEvent, callback)
        event = MyEvent("test")
        self.bus.publish(event)
        callback.assert_called_once_with(event)
        self.bus.unsubscribe(MyEvent, callback)
        callback.reset_mock()
        self.bus.publish(event)
        callback.assert_not_called()

    def test_unsubscribe_non_existent(self):
        callback = Mock()
        # Should not raise error
        self.bus.unsubscribe(MyEvent, callback)
        event = MyEvent("test")
        self.bus.publish(event)
        callback.assert_not_called()

    def test_inheritance_not_propagated(self):
        callback_base = Mock()
        callback_sub = Mock()
        self.bus.subscribe(MyEvent, callback_base)
        self.bus.subscribe(SubEvent, callback_sub)
        event_base = MyEvent("base")
        event_sub = SubEvent("sub")
        self.bus.publish(event_base)
        self.bus.publish(event_sub)
        callback_base.assert_called_once_with(event_base)
        callback_sub.assert_called_once_with(event_sub)
        # Ensure base callback not called for sub event
        self.assertEqual(callback_base.call_count, 1)

    def test_weak_reference_for_methods(self):
        class Subscriber:
            def __init__(self):
                self.called = 0

            def on_event(self, event: MyEvent):
                self.called += 1

        sub = Subscriber()
        self.bus.subscribe(MyEvent, sub.on_event)
        self.assertEqual(len(self.bus._subscribers.get(MyEvent, [])), 1)  # pyright: ignore[reportPrivateUsage]

        event = MyEvent("test")
        self.bus.publish(event)
        self.assertEqual(sub.called, 1)

        del sub
        gc.collect()

        self.bus.publish(event)  # Should clean up dead weak ref
        self.assertEqual(len(self.bus._subscribers.get(MyEvent, [])), 0)  # pyright: ignore[reportPrivateUsage]

    def test_strong_reference_for_functions(self):
        def on_event(event: MyEvent):
            pass

        self.bus.subscribe(MyEvent, on_event)
        self.assertEqual(len(self.bus._subscribers.get(MyEvent, [])), 1)  # pyright: ignore[reportPrivateUsage]

        # Simulate GC, but since strong ref, should remain
        gc.collect()
        self.bus.publish(MyEvent("test"))
        self.assertEqual(len(self.bus._subscribers.get(MyEvent, [])), 1)  # pyright: ignore[reportPrivateUsage]

    def test_unsubscribe_weak_method(self):
        class Subscriber:
            def on_event(self, event: MyEvent):
                pass

        sub = Subscriber()
        self.bus.subscribe(MyEvent, sub.on_event)
        self.assertEqual(len(self.bus._subscribers.get(MyEvent, [])), 1)  # pyright: ignore[reportPrivateUsage]

        self.bus.unsubscribe(MyEvent, sub.on_event)
        self.assertEqual(len(self.bus._subscribers.get(MyEvent, [])), 0)  # pyright: ignore[reportPrivateUsage]


class TestEnrollment(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_enrollment_subscribe_and_publish(self):
        """Test basic Enrollment subscription and publishing"""

        class TestService(Enrollment):
            def __init__(self, event_bus: EventBus):
                super().__init__(event_bus)
                self.received_events: list[Event] = []
                self.subscribe(MyEvent, self.on_my_event)

            def on_my_event(self, event: MyEvent):
                self.received_events.append(event)

        service = TestService(self.bus)
        event = MyEvent("test")
        service.publish(event)

        self.assertEqual(len(service.received_events), 1)
        self.assertEqual(service.received_events[0], event)

    def test_enrollment_multiple_subscriptions(self):
        """Test Enrollment with multiple event type subscriptions"""

        class MultiService(Enrollment):
            def __init__(self, event_bus: EventBus):
                super().__init__(event_bus)
                self.my_events: list[Event] = []
                self.another_events: list[Event] = []
                self.subscribe(MyEvent, self.on_my_event)
                self.subscribe(AnotherEvent, self.on_another_event)

            def on_my_event(self, event: MyEvent):
                self.my_events.append(event)

            def on_another_event(self, event: AnotherEvent):
                self.another_events.append(event)

        service = MultiService(self.bus)
        self.bus.publish(MyEvent("test"))
        self.bus.publish(AnotherEvent(42))

        self.assertEqual(len(service.my_events), 1)
        self.assertEqual(len(service.another_events), 1)

    def test_enrollment_clear_all_subscriptions(self):
        """Test Enrollment.clear() removes all subscriptions"""
        callback_mock = Mock()

        class TestService(Enrollment):
            def __init__(self, event_bus: EventBus):
                super().__init__(event_bus)
                self.subscribe(MyEvent, callback_mock)
                self.subscribe(AnotherEvent, callback_mock)

        service = TestService(self.bus)

        # Verify subscriptions work
        self.bus.publish(MyEvent("test"))
        self.assertEqual(callback_mock.call_count, 1)

        # Clear and verify no more calls
        service.clear()
        callback_mock.reset_mock()
        self.bus.publish(MyEvent("test2"))
        self.bus.publish(AnotherEvent(42))
        callback_mock.assert_not_called()

    def test_enrollment_unsubscribe_specific_event(self):
        """Test Enrollment.unsubscribe() for specific event types"""
        my_callback = Mock()
        another_callback = Mock()

        class TestService(Enrollment):
            def __init__(self, event_bus: EventBus):
                super().__init__(event_bus)
                self.subscribe(MyEvent, my_callback)
                self.subscribe(AnotherEvent, another_callback)

        service = TestService(self.bus)

        # Unsubscribe from MyEvent only
        service.unsubscribe(MyEvent, my_callback)

        self.bus.publish(MyEvent("test"))
        self.bus.publish(AnotherEvent(42))

        my_callback.assert_not_called()
        another_callback.assert_called_once()

    def test_enrollment_unsubscribe_cleans_empty_subscriptions(self):
        """Test that unsubscribing removes empty subscription lists"""
        callback = Mock()

        class TestService(Enrollment):
            def __init__(self, event_bus: EventBus):
                super().__init__(event_bus)
                self.subscribe(MyEvent, callback)

        service = TestService(self.bus)

        # Verify subscription exists
        self.assertIn(MyEvent, service._subscriptions)  # type: ignore[attr-defined]

        # Unsubscribe and verify cleanup
        service.unsubscribe(MyEvent, callback)
        self.assertNotIn(MyEvent, service._subscriptions)  # type: ignore[attr-defined]


# Additional EventBus edge case tests:
class TestEventBusEdgeCases(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_unsubscribe_from_empty_event_type(self):
        """Test unsubscribing when event type has no subscribers"""
        callback = Mock()
        # Should not raise error when event type not in subscribers
        self.bus.unsubscribe(MyEvent, callback)

    def test_publish_removes_dead_weak_references_during_iteration(self):
        """Test that dead weak refs are removed during publish"""

        class Subscriber:
            def on_event(self, event: MyEvent):
                pass

        sub1 = Subscriber()
        sub2 = Subscriber()

        self.bus.subscribe(MyEvent, sub1.on_event)
        self.bus.subscribe(MyEvent, sub2.on_event)

        # Delete one subscriber
        del sub1
        gc.collect()

        # Publishing should clean up dead reference
        initial_count = len(self.bus._subscribers[MyEvent])  # type: ignore[attr-defined]
        self.bus.publish(MyEvent("test"))
        final_count = len(self.bus._subscribers[MyEvent])  # type: ignore[attr-defined]

        self.assertEqual(initial_count, 2)
        self.assertEqual(final_count, 1)


if __name__ == "__main__":
    unittest.main()
