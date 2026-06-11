import gc
import threading
import unittest
from dataclasses import dataclass

from strongbus import Event, EventBus


@dataclass(frozen=True)
class TickEvent(Event):
    n: int


@dataclass(frozen=True)
class OtherEvent(Event):
    n: int


class TestThreadSafety(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_publishes_from_many_threads_all_delivered(self):
        """Every publish from every thread reaches the subscriber exactly once"""
        count_lock = threading.Lock()
        count = [0]

        def on_tick(event: TickEvent) -> None:
            with count_lock:
                count[0] += 1

        self.bus.subscribe(TickEvent, on_tick)

        n_threads, n_events = 8, 250

        def publisher():
            for i in range(n_events):
                self.bus.publish(TickEvent(i))

        threads = [threading.Thread(target=publisher) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(count[0], n_threads * n_events)

    def test_concurrent_duplicate_subscribe_registers_once(self):
        """Set semantics hold under a subscribe race"""
        calls = []

        def cb(event: TickEvent) -> None:
            calls.append(1)

        n_threads = 8
        barrier = threading.Barrier(n_threads)

        def subscriber():
            barrier.wait()
            self.bus.subscribe(TickEvent, cb)

        threads = [threading.Thread(target=subscriber) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.bus.publish(TickEvent(0))
        self.assertEqual(len(calls), 1)

    def test_subscribe_unsubscribe_churn_during_publish(self):
        """Concurrent subscribe/unsubscribe/publish must not raise"""
        errors = []
        stop = threading.Event()

        def sink(event: TickEvent) -> None:
            pass

        self.bus.subscribe(TickEvent, sink)

        def publisher():
            try:
                while not stop.is_set():
                    self.bus.publish(TickEvent(0))
            except Exception as exc:
                errors.append(exc)

        def churner():
            def cb(event: TickEvent) -> None:
                pass

            try:
                for _ in range(300):
                    self.bus.subscribe(TickEvent, cb)
                    self.bus.publish(OtherEvent(1))
                    self.bus.unsubscribe(TickEvent, cb)
            except Exception as exc:
                errors.append(exc)

        publishers = [threading.Thread(target=publisher) for _ in range(3)]
        churners = [threading.Thread(target=churner) for _ in range(3)]
        for t in publishers + churners:
            t.start()
        for t in churners:
            t.join(timeout=60)
        stop.set()
        for t in publishers:
            t.join(timeout=60)

        self.assertEqual(errors, [])

    def test_method_subscribers_dying_during_concurrent_publish(self):
        """Garbage collection of subscribers while other threads publish
        must not raise, and dead entries must all get purged"""
        errors = []
        stop = threading.Event()

        class Subscriber:
            def __init__(self, bus: EventBus):
                bus.subscribe(TickEvent, self.on_event)

            def on_event(self, event: TickEvent) -> None:
                pass

        def publisher():
            try:
                while not stop.is_set():
                    self.bus.publish(TickEvent(0))
            except Exception as exc:
                errors.append(exc)

        def churner():
            try:
                for _ in range(100):
                    sub = Subscriber(self.bus)
                    del sub
                    gc.collect()
            except Exception as exc:
                errors.append(exc)

        publishers = [threading.Thread(target=publisher) for _ in range(3)]
        churners = [threading.Thread(target=churner) for _ in range(2)]
        for t in publishers + churners:
            t.start()
        for t in churners:
            t.join(timeout=60)
        stop.set()
        for t in publishers:
            t.join(timeout=60)

        self.assertEqual(errors, [])

        # All Subscriber instances are gone; one more bus operation must
        # purge every dead entry.
        gc.collect()
        self.bus.publish(TickEvent(0))
        self.assertEqual(len(self.bus._subscribers[TickEvent]), 0)  # pyright: ignore[reportPrivateUsage]

    def test_callback_can_use_bus_without_deadlock(self):
        """Callbacks run outside the bus lock and may re-enter it, even while
        other threads are publishing"""
        done = []

        def chained(event: OtherEvent) -> None:
            done.append(True)

        def reentrant(event: TickEvent) -> None:
            self.bus.subscribe(OtherEvent, chained)
            self.bus.publish(OtherEvent(1))
            self.bus.unsubscribe(OtherEvent, chained)

        self.bus.subscribe(TickEvent, reentrant)

        threads = [
            threading.Thread(target=lambda: self.bus.publish(TickEvent(0)))
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertGreaterEqual(len(done), 4)


if __name__ == "__main__":
    unittest.main()
