#!/bin/bash
# =============================================================================
# check-schema-drift.sh — fail the pipeline if the schema and the scripts have
# stopped agreeing.
#
# The whole design rests on request-schema.yaml being the only place a field is
# declared. Nothing enforces that by itself: someone can add INPUT_NEW_THING to
# a script, wire it up, test it by hand with a CI variable, and ship a field the
# form will never render and OpsDash will never know about. This catches that at
# merge time.
#
#   ./tools/check-schema-drift.sh
#
# Exit 0 clean, 1 on findings.
# =============================================================================
set -e

SCHEMA="${REQUEST_SCHEMA:-./request-schema.yaml}"
SCRIPT_DIR="${1:-./pipeline-scripts}"
FINDINGS=0

finding() {
    echo "  FAIL: $1"
    FINDINGS=$((FINDINGS + 1))
}

command -v yq >/dev/null 2>&1 || { echo "yq is not on PATH."; exit 1; }
[ -f "$SCHEMA" ] || { echo "Schema not found at $SCHEMA"; exit 1; }

echo "==========================================================================="
echo "                          Schema drift check                               "
echo "==========================================================================="

# Everything the schema knows how to set.
DECLARED_ENV=$(
    {
        yq -r '.fields[].env' "$SCHEMA"
        yq -r '.operations[].sets // {} | keys | .[]' "$SCHEMA"
    } | sort -u
)

# Everything the scripts read. load-payload.sh itself is excluded: it names no
# field, it enforces whatever the schema declares.
USED_ENV=$(
    grep -ohE 'INPUT_[A-Z0-9_]+' \
        "$SCRIPT_DIR"/*.sh \
        --exclude='load-payload.sh' 2>/dev/null | sort -u
)

echo ""
echo "-> Every INPUT_* a script reads must be declared in the schema"
for env_name in $USED_ENV; do
    if ! printf '%s\n' "$DECLARED_ENV" | grep -qxF "$env_name"; then
        finding "$env_name is read by a script but not declared in $SCHEMA"
    fi
done

echo "-> Every INPUT_* the schema declares should be read by some script"
for env_name in $DECLARED_ENV; do
    if ! printf '%s\n' "$USED_ENV" | grep -qxF "$env_name"; then
        echo "  WARN: $env_name is declared but no script reads it (dead field?)"
    fi
done

echo "-> Every field an operation lists must exist"
ALL_FIELDS=$(yq -r '.fields | keys | .[]' "$SCHEMA" | sort -u)
for op in $(yq -r '.operations | keys | .[]' "$SCHEMA"); do
    for f in $(yq -r ".operations.\"$op\".fields[]" "$SCHEMA"); do
        printf '%s\n' "$ALL_FIELDS" | grep -qxF "$f" \
            || finding "operation '$op' lists field '$f', which is not declared"
    done
done

echo "-> Every field must have an env, and no two may share one"
DUPES=$(yq -r '.fields[].env' "$SCHEMA" | sort | uniq -d)
[ -z "$DUPES" ] || finding "two fields share an env: $(printf '%s' "$DUPES" | tr '\n' ' ')"
for f in $ALL_FIELDS; do
    e=$(yq -r ".fields.\"$f\".env" "$SCHEMA")
    [ "$e" != "null" ] && [ -n "$e" ] || finding "field '$f' has no env"
done

echo "-> An operation's required list may only name fields it offers"
for op in $(yq -r '.operations | keys | .[]' "$SCHEMA"); do
    OP_FIELDS=$(yq -r ".operations.\"$op\".fields[]" "$SCHEMA")
    for f in $(yq -r ".operations.\"$op\".required // [] | .[]" "$SCHEMA"); do
        printf '%s\n' "$OP_FIELDS" | grep -qxF "$f" \
            || finding "operation '$op' requires '$f' but does not offer it"
    done
done

echo "-> show_if / required_if may only reference declared fields"
for f in $ALL_FIELDS; do
    for which in show_if required_if; do
        for ref in $(yq -r ".fields.\"$f\".$which // {} | keys | .[]" "$SCHEMA"); do
            printf '%s\n' "$ALL_FIELDS" | grep -qxF "$ref" \
                || finding "field '$f' has $which on '$ref', which is not declared"
        done
    done
done

echo "-> A field referenced by show_if must be offered wherever the dependent is"
# Otherwise the condition silently evaluates against a default the operator
# never saw, and the dependent field appears or vanishes for no visible reason.
for op in $(yq -r '.operations | keys | .[]' "$SCHEMA"); do
    OP_FIELDS=$(yq -r ".operations.\"$op\".fields[]" "$SCHEMA")
    for f in $OP_FIELDS; do
        for ref in $(yq -r ".fields.\"$f\".show_if // {} | keys | .[]" "$SCHEMA"); do
            printf '%s\n' "$OP_FIELDS" | grep -qxF "$ref" \
                || finding "operation '$op' offers '$f', whose show_if depends on '$ref' — but '$ref' is not in that operation"
        done
    done
done

# -----------------------------------------------------------------------------
# Schema <-> .gitlab-ci.yml
#
# Added after all three capsule operations shipped in the schema with no CI
# support at all: absent from the OPERATION options, so GitLab refused the input
# outright, and with no scaffold-capsule job to run even if it had not. The form
# offered them, the drift check passed, and every capsule request was
# unrunnable.
#
# The schema is the source of truth; the CI file has to keep up with it.
# -----------------------------------------------------------------------------
CI_FILE="${CI_FILE:-./.gitlab-ci.yml}"

if [ ! -f "$CI_FILE" ]; then
    echo ""
    echo "  WARN: $CI_FILE not found, skipping the CI checks"
else
    SCHEMA_OPS=$(yq -r '.operations | keys | .[]' "$SCHEMA" | sort -u)

    # The CI file is a two-document YAML: the spec header, then the pipeline.
    # `yq ea` would merge them; select each explicitly instead.
    CI_OPTIONS=$(yq -r 'select(document_index == 0) | .spec.inputs.OPERATION.options[]' "$CI_FILE" | sort -u)
    CI_JOBS=$(yq -r 'select(document_index == 1) | keys | .[]' "$CI_FILE" | sort -u)

    echo ""
    echo "-> Every operation in the schema must be an OPERATION option in the CI file"
    for op in $SCHEMA_OPS; do
        printf '%s\n' "$CI_OPTIONS" | grep -qxF "$op" \
            || finding "operation '$op' is in $SCHEMA but not in OPERATION options -- GitLab will refuse it"
    done

    echo "-> Every OPERATION option must be an operation the schema declares"
    for op in $CI_OPTIONS; do
        printf '%s\n' "$SCHEMA_OPS" | grep -qxF "$op" \
            || finding "OPERATION option '$op' is offered by the CI file but not declared in $SCHEMA"
    done

    echo "-> Every job an operation names must exist in the CI file"
    for op in $SCHEMA_OPS; do
        job=$(yq -r ".operations.\"$op\".job // \"\"" "$SCHEMA")
        [ -n "$job" ] || { finding "operation '$op' names no job"; continue; }
        printf '%s\n' "$CI_JOBS" | grep -qxF "$job" \
            || finding "operation '$op' names job '$job', which does not exist in $CI_FILE"
    done

    echo "-> Every job an operation names must actually run for it"
    # A job whose rules exclude the operation is the same failure as a missing
    # job -- a green pipeline with nothing in it -- and that is exactly how an
    # API-driven decommission used to behave.
    for op in $SCHEMA_OPS; do
        job=$(yq -r ".operations.\"$op\".job // \"\"" "$SCHEMA")
        [ -n "$job" ] || continue
        printf '%s\n' "$CI_JOBS" | grep -qxF "$job" || continue
        guard=$(yq -r "select(document_index == 1) | .\"$job\".rules[0].if // \"\"" "$CI_FILE")
        case "$guard" in
            *'$OPERATION !='*)
                # The first rule is the "never for another operation" guard. If
                # it does not name this operation, this operation is excluded.
                printf '%s' "$guard" | grep -qF "\"$op\"" \
                    || finding "operation '$op' runs job '$job', but that job's guard excludes it: $guard"
                ;;
        esac
    done
fi

echo ""
echo "==========================================================================="
if [ "$FINDINGS" -gt 0 ]; then
    echo "  $FINDINGS finding(s). The schema and the scripts have drifted."
    echo "==========================================================================="
    exit 1
fi
echo "  Schema and scripts agree."
echo "==========================================================================="
