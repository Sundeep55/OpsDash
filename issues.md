# Issues

Both issues previously recorded here are fixed and verified; they are kept below
as the record of what went wrong, because the cause is worth not repeating.

## Closed — `yq` silently dropped a literal tab (2 occurrences)

**Symptom.** `ERROR: Could not read any fields from request-schema.yaml`, on a
merge to main and again on a form-triggered pipeline. The schema parsed as empty.

**Cause.** `load-payload.sh` built its field table with `"\t"` inside a `yq`
expression. Older `yq` exits 0 and emits no tab at all, so every line came back
unsplittable and the schema looked like it had no fields. It appeared twice —
once in the table builder, once in `_lp_load_payload`.

**Fix.** `strenv(LP_SEP)` with the separator exported from the shell, so the tab
is data rather than something `yq` has to interpret. 13 occurrences today. The
`2>/dev/null` that had hidden the diagnosis was removed, and a failure now prints
the `yq` version and the first raw line through `cat -v`.

**Guard.** `tools/test-cases.sh` catches this class. It is not in CI on purpose
(see the note in `.gitlab-ci.yml`) — run it locally when changing the schema, the
shim or the form.
