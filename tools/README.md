# Verification tools

There is no test suite. These two scripts stand in for one when changing
`sync_gitops` or the API layer: they let you prove a refactor produced the same
database and the same API responses, rather than eyeballing it.

## gitops_fixture.py

Writes a synthetic GitOps repo that exercises every branch of the sync walk --
provisioner config, egress/CSO, service mesh, registry mirrors, GPU config
(enabled and disabled), custom resource templates, tenant metadata, a siglum
override that differs from its tenant's, decommissioned tenants and namespaces,
and a deliberately malformed YAML file that must be skipped without aborting
the run.

```
python tools/gitops_fixture.py /tmp/fixture
```

Add `--scale <tenants>,<namespaces>` for a production-sized repo on top of the
correctness cases, for measuring behaviour under real row counts:

```
python tools/gitops_fixture.py /tmp/fixture-big --scale 298,797
```

Bulk data is shaped like the real repo -- most namespaces carry only a
provisioner block and one chart dependency, a minority add operators, templates
or mirrors.

## api_snapshot.py

Dumps every model table and every API response to a directory as sorted JSON.

```
DJANGO_ALLOWED_HOSTS=testserver PYTHONPATH=. python tools/api_snapshot.py /tmp/before
```

## mutation_check.py

Syncs a fixture, mutates it the way Git would change over time, re-syncs, and
asserts the database followed. This catches a whole class of bug a single sync
cannot: records that are only ever created or set, never updated or removed --
an operator deleted from `managedServices`, a tenant moved back out of
`.decommissioned_tenants/`, a namespace reassigned to a different tenant.

```
PYTHONPATH=. python tools/mutation_check.py /tmp/fixture /tmp/fixture-mutated
```

Exits non-zero if any assertion fails.

## Typical use

```bash
python tools/gitops_fixture.py /tmp/fixture

# baseline, before the change
export DATABASE_PATH=/tmp/before.sqlite3 DJANGO_ALLOWED_HOSTS=testserver PYTHONPATH=.
python manage.py migrate --noinput
python manage.py sync_gitops --repo-path /tmp/fixture
python tools/api_snapshot.py /tmp/snap_before

# ... make the change, then repeat into /tmp/snap_after ...

diff -r /tmp/snap_before /tmp/snap_after
```

`_db.json` rows are sorted by full content and `_api.json` keys are sorted, so
ordering never produces a false diff.

Three differences are expected and do not indicate a regression:

- `SystemSyncStatus.last_sync_time` and the sync-status endpoint — a wall-clock
  timestamp, different on every run.
- `routeException.daysActive` on any namespace with an active route exception —
  it is `(today - granted_at).days`, so it increments at every midnight. If you
  compare snapshots taken on different days, every endpoint carrying a
  namespace payload will differ by this one field.

A refactor that is meant to preserve behaviour should produce no other
difference. Anything else is a bug in the refactor, not an improvement.
