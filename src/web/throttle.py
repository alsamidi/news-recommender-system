"""Simple in-memory login throttling.

Design fixed by ARCHITECTURE.md §6: count failures per email within a window.
In-memory is sufficient for the MVP (single process); a multi-worker deployment
would need a shared store, which is noted in SECURITY_NOTES.md.

This is intentionally crude: it slows online guessing without locking accounts
permanently, and it never reveals whether an email exists.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 5
# Per-IP budget. Deliberately six times the per-email budget: one address is
# not one person (campus NAT, office, mobile carrier gateway). A shared address
# must not lock out bystanders because one person mistyped. 30 in 15 minutes
# still caps automated guessing at ~2 attempts/minute.
IP_MAX_FAILURES = 30


class LoginThrottle:
    def __init__(self, window_seconds: int = WINDOW_SECONDS,
                 max_failures: int = MAX_FAILURES):
        self.window = window_seconds
        self.max_failures = max_failures
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        cutoff = now - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def is_blocked(self, key: str) -> bool:
        """True when this key has exhausted its attempts in the window."""
        now = time.monotonic()
        return len(self._prune(key, now)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        q = self._prune(key, now)
        q.append(now)

    def reset(self, key: str) -> None:
        """Clear on successful login so a legitimate user is never punished."""
        self._failures.pop(key, None)

    def retry_after(self, key: str) -> int:
        """Seconds until the oldest failure leaves the window (min 1)."""
        now = time.monotonic()
        q = self._prune(key, now)
        if not q:
            return 0
        return max(1, int(self.window - (now - q[0])) + 1)
