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

---

## demo_estate.py — a browsable estate, at scale

`gitops_fixture.py` is small on purpose: every branch of the sync walk is
visible and assertable in it. It is not useful for looking at the dashboard,
because three rows tell you nothing about how a list of eight hundred behaves.

`demo_estate.py` is the other half — a generated estate roughly the size of
production, for exercising the UI by hand: pagination, the siglum drill-down,
the expiry banner, cluster scoping, long tenant rosters, empty states.

```bash
python3 tools/demo_estate.py /tmp/demo-estate

export DATABASE_PATH=/tmp/demo.sqlite3      # keep it out of your real db.sqlite3
python manage.py migrate --noinput
python manage.py sync_gitops --repo-path /tmp/demo-estate
python manage.py createsuperuser
python manage.py runserver 8861
```

No GitLab involved. The sync falls back to `--repo-path` whenever `GITLAB_URL`,
`GITLAB_TOKEN` and `GITLAB_PROJECT_ID` are not all set, which an ordinary
development shell already satisfies — see `dashboard/gitops/fetcher.py`.

`DATABASE_PATH` is the important line. Without it the sync writes into the
`db.sqlite3` in the repository root and replaces whatever is there.

Deterministic: the same seed gives the same estate, so a screenshot taken today
still matches tomorrow. `--tenants N` changes the size, `--seed N` the shape.

It deliberately generates things the small fixture does not, because they are
the parts that only misbehave at scale or over time:

- route exceptions spread across active, expiring-within-30-days and expired,
  so the banner has real content rather than never firing
- capsules, which `gitops_fixture.py` does not cover at all
- a long-tailed namespace distribution — most tenants small, a few large
- decommissioned tenants and namespaces, so those filters return something
- siglums in a two-level hierarchy, so the drill-down has depth to drill

The printed summary is what was written to disk. The sync will report slightly
more namespaces than that: a service mesh names dataplane members that do not
otherwise exist and the walk creates them, which is the behaviour being
exercised rather than a miscount.

### Driving the trigger form without a GitLab

`PIPELINE_SCHEMA_FILE` puts the pipeline feature into a dry run: the schema is
read from a local file, and pressing "Start pipeline" prints the request to the
server console instead of sending it. There is no code path from that mode to
the network — `trigger()` returns before a request object is built.

Generate an estate together with a matching schema:

```bash
python3 tools/demo_estate.py /tmp/demo-estate --schema /tmp/demo-schema.yaml
```

`--schema` copies `request-schema.yaml` with `target_cluster` repointed at the
clusters it just generated, so the form's tenant and namespace picklists resolve
against the estate. It is edited as text rather than parsed and re-emitted,
because the schema's comments are the documentation for every field and a YAML
round trip would drop all of them.

```bash
export DATABASE_PATH=/tmp/demo.sqlite3
export PIPELINE_ENABLED=true PIPELINE_SCHEMA_FILE=/tmp/demo-schema.yaml
python manage.py runserver 8862
```

The dialog says "Dry run" in its footer and on the confirmation, so a request
that went nowhere is never mistaken for one that did. Output looks like:

```
========================================================================
PIPELINE DRY RUN #1 -- nothing was sent to GitLab
  OPERATION    = namespace.create
  TRIGGERED_BY = demo <demo@example.com>
  REQUEST_PAYLOAD =
      namespace_name  = anvil-reports
      ...
  (594 bytes as one CI input value)
========================================================================
```

Printed rather than logged at DEBUG: reading the payload is the entire reason
the mode exists, and it prints only when the mode is on, so a normal deployment
is unaffected.
