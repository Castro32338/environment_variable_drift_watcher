from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class DriftEvent:
    """A single observed change to one environment variable.

    Frozen so that downstream consumers cannot mutate events that have already been
    recorded — a real hazard once events are handed to logging pipelines or queues.

    Either `old_value` or `new_value` (but never both) may be None, representing a
    variable that has been newly added or entirely removed. Representing these
    states with None rather than a sentinel string avoids any ambiguity about whether
    a real environment variable happened to equal the sentinel text.
    """

    key: str
    old_value: Optional[str]
    new_value: Optional[str]
    observed_at: float


class DriftWatcher:
    """Periodically snapshots process environment variables and reports changes.

    This watcher is deliberately about detecting mutation of a running process's
    environment — the situation where code calls os.putenv or os.environ assignment
    after startup, silently changing behaviour mid-run. It is not a general env-diff
    tool; it compares against the state at the previous snapshot, not against a
    fixed golden file.

    Determinism contract: pass a `clock` callable returning a numeric timestamp.
    The default uses time.monotonic because it is immune to wall-clock adjustments,
    which keeps event ordering stable on machines whose clocks jump. Tests inject
    their own clock to avoid dependence on wall time.
    """

    def __init__(
        self,
        *,
        environ: Optional[Mapping[str, str]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if environ is None:
            environ = os.environ
        # We hold a private copy of the mapping at snapshot time. Reading from
        # os.environ directly on each comparison would miss changes that go through
        # os.putenv, which does not update os.environ on all platforms. Accepting an
        # injectable environ makes the tests deterministic and lets callers scope
        # observation to a dict they control.
        self._environ_source = environ
        if clock is None:
            import time

            clock = time.monotonic
        self._clock = clock
        self._previous: Optional[Dict[str, str]] = None
        self._events: List[DriftEvent] = []

    def _snapshot(self) -> Dict[str, str]:
        return dict(self._environ_source)

    def snapshot(self) -> Tuple[DriftEvent, ...]:
        """Take a snapshot and return any drift events since the previous snapshot.

        The first call establishes the baseline and returns an empty tuple; no
        event is emitted for the initial state because there is no prior value
        against which to detect a change.
        """
        current = self._snapshot()
        if self._previous is None:
            self._previous = current
            self._events = []
            return tuple()

        now = self._clock()
        new_events: List[DriftEvent] = []

        # Sort keys so that event order is deterministic across platforms and
        # dict insertion orders. Several tests assert on the relative order of
        # events and would be flaky without this.
        all_keys = set(current) | set(self._previous)
        for key in sorted(all_keys):
            old_value = self._previous.get(key)
            new_value = current.get(key)
            if old_value != new_value:
                new_events.append(
                    DriftEvent(
                        key=key,
                        old_value=old_value,
                        new_value=new_value,
                        observed_at=now,
                    )
                )

        self._previous = current
        self._events.extend(new_events)
        return tuple(new_events)

    @property
    def events(self) -> Tuple[DriftEvent, ...]:
        """All drift events recorded by this watcher, in observation order."""
        return tuple(self._events)

    def reset(self) -> None:
        """Clear all recorded events and the baseline.

        After reset, the next call to snapshot() re-establishes the baseline and
        returns an empty tuple. This is useful in long-running processes that want
        a clean slate after consuming events, without restarting the watcher.
        """
        self._previous = None
        self._events = []
