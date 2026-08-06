#!/usr/bin/env python3
"""Liveness check for the polling sidecar, for use as an exec probe.

The sidecar serves no HTTP, so there is nothing for an httpGet probe to hit.
It instead touches a heartbeat file at the end of every poll iteration; this
script fails if that file has gone stale, which is the only externally visible
sign that the loop has wedged.

Deliberately stdlib-only and free of any Django import. A probe runs every few
seconds for the life of the pod, and paying Django's startup cost each time --
including opening the SQLite file the sync is writing -- would cost more than
the check is worth.

    python3 bin/sidecar_health.py [max_age_seconds]

Exit 0 healthy, 1 stale or missing. Default max age is derived from
POLL_INTERVAL_SECONDS so it does not need updating when the interval changes.
"""
import os
import sys
import time

DEFAULT_POLL_INTERVAL = 60

# Multiple of the poll interval. Generous on purpose: one slow GitLab call, or
# a full sync triggered mid-loop, must not be mistaken for a wedged daemon.
# Restarting during a sync would leave the lock held until it goes stale.
STALENESS_FACTOR = 6

# Floor for very short poll intervals, so a 5s interval does not give the
# baseline sync a 30s deadline it cannot meet at full scale.
MINIMUM_MAX_AGE = 300


def max_age_seconds():
    if len(sys.argv) > 1:
        return int(sys.argv[1])
    try:
        interval = int(os.environ.get('POLL_INTERVAL_SECONDS', DEFAULT_POLL_INTERVAL))
    except ValueError:
        interval = DEFAULT_POLL_INTERVAL
    return max(interval * STALENESS_FACTOR, MINIMUM_MAX_AGE)


def main():
    path = os.environ.get('SIDECAR_HEARTBEAT_PATH', '/tmp/sidecar-heartbeat')
    limit = max_age_seconds()

    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        # Absent on a cold start too, but the daemon writes it before the
        # baseline sync, so initialDelaySeconds covers that window.
        print(f"UNHEALTHY: no heartbeat at {path}", file=sys.stderr)
        return 1

    if age > limit:
        print(f"UNHEALTHY: heartbeat {age:.0f}s old, limit {limit}s", file=sys.stderr)
        return 1

    print(f"ok: heartbeat {age:.0f}s old (limit {limit}s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
