# Changelog

Notable changes to strongbus. History before 0.3.0 is in the git log.

## [0.3.0] - Unreleased

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
- The `dev` extra now includes `tox-uv`, so `uv run --extra dev tox` works
  out of the box. The `lint` tox env is a pure check; auto-fixing moved to a
  new `fix` env, and CI now enforces lint and typecheck.

### Added

- `PublishError`, exported from the package root.
- Trove classifiers in the packaging metadata.

### Documentation

- `unsubscribe` is not a delivery barrier: a publish already in flight on
  another thread may still invoke the callback once after `unsubscribe`
  returns.
- Subscription set semantics are bus-level: two Enrollments on the same bus
  subscribing the same callback object share a single subscription.
