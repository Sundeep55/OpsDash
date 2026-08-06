# Adding a `values.yaml` section

When the provisioner chart grows a new config block, this is how it reaches the
dashboard.

> **Names in this document are placeholders.** `namespace-provisioner`,
> `tenant-metadata.yaml`, `Chart.yaml` and the rest are the defaults used by the
> fixtures; the real repository uses different ones. They are all declared in
> `GITOPS_LAYOUT` in `ops_portal/settings.py` and overridable per environment
> variable, so nothing below needs editing when a name differs — see
> `dashboard/gitops/layout.py`.
>
> The keys *inside* a block (`resourceQuota`, `gpuConfig`, `requiredLabels` …)
> are real and are matched literally by the section registry.

For the common shape — a block with an on/off key and some scalar fields — it is
**a model and one registry entry**. No parser function, no serializer field, no
template. The API publishes it and the detail page renders it.

## The common case

Say the chart adds:

```yaml
namespace-provisioner:
  backupConfig:
    enabled: true
    schedule: "0 3 * * *"
    retentionDays: "30"
    s3:
      bucket: ops-backups-prod
```

### 1. A model

In `dashboard/models.py`. One row per namespace, so `OneToOneField`:

```python
class BackupPolicy(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='backup_policy')
    schedule = models.CharField(max_length=100, null=True, blank=True)
    retention_days = models.IntegerField(default=0)
    target_bucket = models.CharField(max_length=255, null=True, blank=True)
```

Store repo values verbatim. Quantities like `"4"`, `16Gi` and `0 3 * * *` stay
`CharField` — the repo quotes them inconsistently and guessing at units loses
information.

### 2. A registry entry

In `dashboard/gitops/sections.py`, added to `SECTIONS`:

```python
Section(
    name='backup',
    title='Backup Policy',
    yaml_key='backupConfig',
    model=BackupPolicy,
    fields=(
        Field('schedule', 'schedule'),
        Field('retention_days', 'retentionDays', default=0, cast=to_int),
        Field('target_bucket', 's3.bucket'),
    ),
    labels={'retention_days': 'Retention (days)', 'target_bucket': 'S3 Bucket'},
),
```

Points worth knowing:

- **`source` may be dotted.** `s3.bucket` reads the nested block; a missing hop
  yields the default rather than raising.
- **`cast` runs only on a value that is present.** The repo quotes numbers
  (`retentionDays: "30"`), so numeric fields need `cast=to_int`. Without it the
  string reaches an `IntegerField` and the whole file is skipped.
- **`gate` defaults to `('enabled',)`.** Harbor spells its gate `enable`, which
  is why that entry overrides it. Pass `gate=None` for a block that always
  applies.
- **A closed gate deletes the row.** Absence in Git means the feature was
  removed, so the record goes rather than lingering as stale state.
- **`labels` is optional.** Field names are prettified (`retention_days` →
  "Retention Days") when no label is given.

### 3. Migration

```bash
python manage.py makemigrations dashboard
```

Commit the migration. Do not generate them at runtime.

### That's it

Sync, and the block is parsed, stored, published under `sections` in
`/api/v2/namespaces/<name>/`, and rendered as a card on the detail page with
your title and labels.

```bash
python tools/gitops_fixture.py /tmp/fixture     # add the block to a namespace
python manage.py sync_gitops --repo-path /tmp/fixture
```

## When it is not the common case

Some shapes cannot be declared: a list of children, a dict of arbitrary keys, or
a rule that depends on another section. Those get a function in
`dashboard/gitops/parsers/provisioner.py` and are called from
`_apply_provisioner`.

**Still add them to `SECTIONS`**, with `implemented_by` naming where the code
lives. The registry is the index of every block the sync understands; a section
missing from it is a section nobody can find. Existing examples:

| Section | Why it is bespoke |
|---|---|
| `network_flows` | Also writes a list of `NetworkConnection` children |
| `routeException` | Must not overwrite a grant made by `tenant-metadata.yaml` |
| `operators` | A dict of operator name → `{enabled}`, one row each |
| `robotAccounts` | A list of children, replaced wholesale |
| `userAccess` | Two sibling blocks feeding one model |

A bespoke section also needs its own serializer field and template markup — set
`auto_render=False` so the generic renderer does not publish it twice.

## Custom UI for a simple section

If a section is declarative but deserves richer markup than a field grid — a
progress bar, an icon, a colour-coded badge — set `auto_render=False` and add
the card to `dashboard/templates/dashboard/tabs/namespaces/detail.html` plus a
serializer field in `dashboard/serializers/core.py`. That is what compute
limits, GPU and Harbor do.

## Before you commit

```bash
python manage.py makemigrations --check --dry-run   # migration committed?
python manage.py build_css --check                  # new CSS classes present?
python -m pyflakes dashboard/
```

`build_css --check` matters if you touched a template: the vendored Tailwind
build only contains the utilities that existed when it ran, so a new class
silently renders as nothing unless it is regenerated. That check also runs in
the Docker build, so a miss fails the image rather than shipping unstyled.

To confirm you did not change existing behaviour:

```bash
python tools/api_snapshot.py /tmp/after
diff -r /tmp/before /tmp/after
```

See `tools/README.md`.
