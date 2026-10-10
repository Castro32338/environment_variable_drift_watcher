"""environment_variable_drift_watcher: snapshot process env and emit drift events.

Why re-export from __init__?

Importing at the package root is the most stable public surface. We deliberately keep
the internal module name (core) out of the public docs so that future restructuring
does not break user imports like `from environment_variable_drift_watcher import DriftWatcher`.
"""

from .core import (
    DriftEvent,
    DriftWatcher,
)

__all__ = [
    "DriftEvent",
    "DriftWatcher",
]
