import unittest

from environment_variable_drift_watcher import DriftEvent, DriftWatcher


class FakeClock:
    """A clock whose time advances only when we explicitly tick it.

    Using this lets tests assert on event ordering and timestamps without ever
    touching wall-clock time. Wall-clock dependence is the single most common
    source of flaky tests for time-sensitive code, so we refuse it entirely.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


class DriftWatcherTests(unittest.TestCase):
    def test_first_snapshot_is_baseline_and_returns_no_events(self) -> None:
        clock = FakeClock()
        env = {"FOO": "1", "BAR": "2"}
        watcher = DriftWatcher(environ=env, clock=clock)

        events = watcher.snapshot()

        self.assertEqual(events, ())
        self.assertEqual(watcher.events, ())

    def test_value_change_emits_event(self) -> None:
        clock = FakeClock()
        env = {"FOO": "1"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        clock.advance(5.0)
        env["FOO"] = "2"

        events = watcher.snapshot()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].key, "FOO")
        self.assertEqual(events[0].old_value, "1")
        self.assertEqual(events[0].new_value, "2")
        self.assertEqual(events[0].observed_at, 5.0)

    def test_added_variable_emits_event_with_none_old_value(self) -> None:
        clock = FakeClock()
        env: dict = {}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        env["NEW"] = "x"

        events = watcher.snapshot()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].key, "NEW")
        self.assertIsNone(events[0].old_value)
        self.assertEqual(events[0].new_value, "x")

    def test_removed_variable_emits_event_with_none_new_value(self) -> None:
        clock = FakeClock()
        env = {"GONE": "v"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        del env["GONE"]

        events = watcher.snapshot()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].key, "GONE")
        self.assertEqual(events[0].old_value, "v")
        self.assertIsNone(events[0].new_value)

    def test_multiple_changes_emit_events_in_sorted_key_order(self) -> None:
        clock = FakeClock()
        env = {"A": "1", "B": "2", "C": "3"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        clock.advance(1.0)
        env["A"] = "10"
        env["C"] = "30"
        env["D"] = "40"
        del env["B"]

        events = watcher.snapshot()

        self.assertEqual([e.key for e in events], ["A", "B", "C", "D"])
        self.assertEqual(events[0].old_value, "1")
        self.assertEqual(events[0].new_value, "10")
        self.assertEqual(events[1].old_value, "2")
        self.assertIsNone(events[1].new_value)
        self.assertEqual(events[2].old_value, "3")
        self.assertEqual(events[2].new_value, "30")
        self.assertIsNone(events[3].old_value)
        self.assertEqual(events[3].new_value, "40")

    def test_no_changes_returns_empty_tuple(self) -> None:
        clock = FakeClock()
        env = {"X": "1"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        clock.advance(2.0)

        events = watcher.snapshot()

        self.assertEqual(events, ())

    def test_events_property_accumulates_across_snapshots(self) -> None:
        clock = FakeClock()
        env = {"K": "a"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        clock.advance(1.0)
        env["K"] = "b"
        first = watcher.snapshot()
        clock.advance(1.0)
        env["K"] = "c"
        second = watcher.snapshot()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(len(watcher.events), 2)
        self.assertEqual(watcher.events[0].new_value, "b")
        self.assertEqual(watcher.events[1].new_value, "c")

    def test_reset_clears_events_and_baseline(self) -> None:
        clock = FakeClock()
        env = {"K": "a"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        env["K"] = "b"
        watcher.snapshot()
        self.assertEqual(len(watcher.events), 1)

        watcher.reset()

        self.assertEqual(watcher.events, ())
        events = watcher.snapshot()
        self.assertEqual(events, ())
        env["K"] = "c"
        after = watcher.snapshot()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].old_value, "b")
        self.assertEqual(after[0].new_value, "c")

    def test_change_back_to_original_value_between_snapshots_emits_no_event(
        self,
    ) -> None:
        clock = FakeClock()
        env = {"K": "a"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        env["K"] = "b"
        env["K"] = "a"

        events = watcher.snapshot()

        self.assertEqual(events, ())

    def test_snapshot_returns_only_new_events_not_full_history(self) -> None:
        clock = FakeClock()
        env = {"K": "a"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        clock.advance(1.0)
        env["K"] = "b"
        first = watcher.snapshot()
        clock.advance(1.0)
        second = watcher.snapshot()

        self.assertEqual(len(first), 1)
        self.assertEqual(second, ())

    def test_event_is_immutable(self) -> None:
        clock = FakeClock()
        env = {"K": "a"}
        watcher = DriftWatcher(environ=env, clock=clock)
        watcher.snapshot()
        env["K"] = "b"
        events = watcher.snapshot()

        with self.assertRaises(Exception):
            events[0].key = "OTHER"  # type: ignore[misc]

    def test_uses_os_environ_by_default(self) -> None:
        import os

        key = "DRIFT_WATCHER_TEST_KEY"
        self.assertNotIn(key, os.environ)
        try:
            os.environ[key] = "1"
            watcher = DriftWatcher()
            watcher.snapshot()
            os.environ[key] = "2"
            events = watcher.snapshot()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].key, key)
            self.assertEqual(events[0].old_value, "1")
            self.assertEqual(events[0].new_value, "2")
        finally:
            os.environ.pop(key, None)


if __name__ == "__main__":
    unittest.main()
