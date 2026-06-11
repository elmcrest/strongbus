# Changelog

Notable changes to strongbus. History before 0.3.0 is in the git log.

## [0.3.1] - 2026-06-11

### Changed

- `subscribe` and `subscribe_global` (on the bus and on `Enrollment`) now
  raise `TypeError` when given a coroutine function. `publish` calls
  subscribers synchronously and never awaits, so an `async def` callback
  would only ever produce an unawaited coroutine; the mistake is now caught
  at subscribe time instead of failing silently on every publish.

## [0.3.0] - 2026-06-11

### Changed

- **Breaking:** dropped support for Python 3.10; strongbus now requires
  Python 3.11+.
- A subscriber that raises no longer prevents delivery to the remaining
  subscribers. `publish` notifies everyone first, then re-raises a single
  failure unchanged, or raises the new `PublishError` (an `ExceptionGroup`
  subclass that works with `except*`) when several subscribers raised.
- `subscribe` and `unsubscribe` now raise `TypeError` when `event_type` is
  not an `Event` subclass. Previously such subscriptions registered silently
  and never fired.
- `Enrollment` tracks bound methods weakly, mirroring the bus's reference
  policy: tracking another object's bound method no longer keeps that object
  alive, and self-subscribing enrollments no longer form a reference cycle.
- `Enrollment` no longer inherits from `abc.ABC` (it declared no abstract
  methods, so it was already instantiable).
- Callbacks are matched by identity (bound methods by the instance and
  function they wrap) instead of `==`. A callable with a custom `__eq__` can
  no longer be silently deduplicated against - or unsubscribed in place of -
  a different handler.
- Dead-reference cleanup now also drops emptied event-type keys, so a
  dynamically created event class is no longer kept alive after its last
  subscriber is gone.
- `EventBus.subscribe` and `EventBus.subscribe_global` now return a bool:
  `True` if the callback was newly subscribed, `False` if it was already
  subscribed.
- The sdist no longer ships repo tooling (`.github`, `.vscode`,
  `.python-version`, `CLAUDE.md`); tests, `tox.ini`, and `uv.lock` remain
  included.
- The `dev` extra now includes `tox-uv`, so `uv run --extra dev tox` works
  out of the box. The `lint` tox env is a pure check; auto-fixing moved to a
  new `fix` env, and CI now enforces lint and typecheck.

### Fixed

- `Enrollment.unsubscribe` and `Enrollment.unsubscribe_global` no longer
  remove a bus subscription the enrollment never made. Previously they
  delegated to the bus unconditionally, so an enrollment could unsubscribe
  a callback that another owner had registered directly on the bus.
- `Enrollment.subscribe` and `Enrollment.subscribe_global` no longer take
  ownership of a subscription that already existed on the bus. When the
  bus-level subscribe is a no-op, the enrollment does not track the
  callback, so `clear()` and `unsubscribe` leave the original subscription
  in place. Previously, whichever enrollment cleared first removed a shared
  subscription for everyone.

### Added

- `PublishError`, exported from the package root.
- Trove classifiers in the packaging metadata.

### Documentation

- `unsubscribe` is not a delivery barrier: a publish already in flight on
  another thread may still invoke the callback once after `unsubscribe`
  returns.
- Subscription set semantics are bus-level: a callback is subscribed to an
  event type at most once per bus, however many enrollments subscribe it;
  the subscription is owned - and removed - by whoever created it.
- Identity matching implies linear-scan bookkeeping: `subscribe` and
  `unsubscribe` are linear in the event type's subscriber count.
