# environment_variable_drift_watcher

Periodically snapshots process environment variables and emits a structured event when any observed value changes at runtime after startup.

```python
from environment_variable_drift_watcher import DriftWatcher, DriftEvent

watcher = DriftWatcher()
watcher.snapshot()  # establish baseline; returns ()

import os
os.environ["FEATURE_FLAG"] = "on"

events = watcher.snapshot()  # (DriftEvent(key="FEATURE_FLAG", old_value=None, new_value="on", observed_at=...),)
for e in events:
    print(f"{e.key}: {e.old_value!r} -> {e.new_value!r} at {e.observed_at}")
```

## Why

Long-running processes sometimes mutate their own environment variables mid-run via `os.putenv` or direct assignment to `os.environ`. Those changes are invisible at the call site and can silently alter behaviour of any code that reads the environment later. This watcher gives you a hook to detect that drift by comparing successive snapshots.

The trade-off: it compares against the previous snapshot, not against a golden baseline persisted to disk. That keeps the library dependency-free and the API small, but means it cannot tell you that a value differs from what you intended at deploy time — only that it changed since the last call to `snapshot()`.

## Edge you will hit

If a variable is set to a new value and then set back to its original value between two snapshots, no event is emitted. The watcher reports net change, not the intermediate history. If you need a full audit trail of every mutation, call `snapshot()` more frequently — but never inside a hot loop without measuring the cost first, since each call copies the entire environment.
