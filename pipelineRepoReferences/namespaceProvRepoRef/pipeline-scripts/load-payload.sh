#!/bin/bash
# =============================================================================
# load-payload.sh — turn OPERATION + REQUEST_PAYLOAD into the INPUT_* variables
# the scaffold and decommission scripts already expect.
#
#   source "$(dirname "$0")/load-payload.sh"
#
# Sourced, not executed: it exports into the calling script's own environment,
# so there is no `eval` of generated text and no dotenv artifact in the way.
#
# WHY THIS EXISTS
# ---------------
# The CI file used to declare 25 separate inputs, and GitLab enforced their
# types and option lists server-side before any script ran. GitLab also caps a
# pipeline at 20 *changed* input values on every path including the web UI, and
# a maximal prod request already changed exactly 20 — no room to merge the
# registry-mirror pipeline in, and none for HCP.
#
# Collapsing to one JSON payload removes that ceiling. It also removes GitLab's
# enforcement, so this script has to put it back. That is the load-bearing part:
# without the checks below, a typo'd target cluster that GitLab would have
# rejected outright would instead reach `mkdir -p` and quietly create a new
# top-level cluster directory.
#
# The scripts that source this file are unchanged in this respect. They still
# read INPUT_* and have no idea the payload exists.
#
# REQUIREMENTS
# ------------
# yq v4 (already in pipeline-tools; `yq -p json` parses the payload, so nothing
# new has to be installed on an airgapped runner). Bash 3.2 compatible on
# purpose — no associative arrays, no ${x,,} — so it can be run and tested
# outside the CI image.
#
# The schema and the payload are each read with a single yq invocation and
# cached in shell variables. The straightforward version, one yq call per
# property, took 7.4 seconds per run; this takes well under one.
# =============================================================================

_LP_SCHEMA="${REQUEST_SCHEMA:-./request-schema.yaml}"
_LP_NL='
'

_lp_die() {
    echo "" >&2
    echo "===========================================================================" >&2
    echo "ERROR: $1" >&2
    echo "===========================================================================" >&2
    echo "" >&2
    exit 1
}

# Shell variable names are built from field and operation names. Field names are
# validated against ^[a-z][a-z0-9_]*$ as they are read, so they are already safe
# to use verbatim; only operation names need folding, and only once per run.
_lp_key() { local s="$1"; printf '%s' "${s//[!a-zA-Z0-9_]/_}"; }

_lp_put()  { eval "_LPD_$1=\$2"; }
_lp_add()  {
    local cur; eval "cur=\${_LPD_$1}"
    if [ -z "$cur" ]; then eval "_LPD_$1=\$2"; else eval "_LPD_$1=\"\$cur\$_LP_NL\$2\""; fi
}

# ---------------------------------------------------------------------------
# Accessors assign into a variable named by their last argument rather than
# echoing a result.
#
# This is not style: `x=$(_lp_prop ...)` forks a subshell, and these are called
# on the order of a thousand times per run -- once per schema line, then once
# per field per property in each of four passes. Echoing versions took 34
# seconds per invocation on a development machine and made the 50-case suite
# time out; assigning takes well under a second. yq itself is 0.4s of that.
# ---------------------------------------------------------------------------
_lp_val_into()  { eval "$2=\${_LPD_$1}"; }
_lp_prop_into() { eval "$3=\${_LPD_F_$1__$2}"; }   # scalar property of a field
_lp_list_into() { eval "$3=\${_LPD_L_$1__$2}"; }   # options/deny_prefix/show_if/required_if
_lp_get_into()  { eval "$2=\${_LPV_$1}"; }         # resolved value
_lp_flag_into() { eval "$3=\${_LPF_$1_$2}"; }      # present/hidden flag

# ---------------------------------------------------------------------------
# One yq call. Emits a flat, separator-delimited description of everything below.
#
# CONSTRUCT CHOICE MATTERS HERE, and this function has been wrong twice.
#
# 1. The separator comes from strenv(LP_SEP), not from a "\t" literal in the
#    expression. Older yq builds do not interpret escape sequences inside
#    string concatenation: they exit 0 and emit the line *without* a tab, so
#    every line parses as one field, nothing matches, and the schema reads as
#    empty. That is a silent failure with a useless error, and it is what broke
#    the first deployment. strenv() is used throughout the original scaffold
#    scripts, so it is proven against the pipeline-tools image.
#
# 2. Scalars are selected by deleting the known structured keys rather than by
#    testing tag. An `or` chain over tag silently dropped every boolean once
#    already, which made `required: true` invisible and meant nothing was ever
#    required. del() is likewise proven in the original scripts.
#
# Prefer a construct the pre-existing scripts already use. If you must add a
# new one, make sure its failure mode is loud -- see the checks below.
#
# A structured key added to the schema in future and not listed in the del()
# chain would be emitted as a JSON blob into a property nothing reads. Harmless,
# but add it to the chain.
# ---------------------------------------------------------------------------
_lp_load_schema() {
    local kind a b c raw rc

    LP_SEP=$(printf '\t')
    export LP_SEP

    raw=$(yq -r '
      ( .fields     | to_entries[] | "N" + strenv(LP_SEP) + .key ),
      ( .operations | to_entries[] | "Q" + strenv(LP_SEP) + .key ),
      ( .fields | to_entries[] | .key as $f | .value
          | del(.options) | del(.deny_prefix) | del(.show_if) | del(.required_if) | del(.source)
          | to_entries[]
          | "F" + strenv(LP_SEP) + $f + strenv(LP_SEP) + .key + strenv(LP_SEP) + (.value | tostring) ),
      ( .fields | to_entries[] | .key as $f | (.value.options     // [])[]
          | "O" + strenv(LP_SEP) + $f + strenv(LP_SEP) + . ),
      ( .fields | to_entries[] | .key as $f | (.value.deny_prefix // [])[]
          | "D" + strenv(LP_SEP) + $f + strenv(LP_SEP) + . ),
      ( .fields | to_entries[] | .key as $f | (.value.show_if     // {}) | to_entries[]
          | "S" + strenv(LP_SEP) + $f + strenv(LP_SEP) + .key + strenv(LP_SEP) + (.value | tostring) ),
      ( .fields | to_entries[] | .key as $f | (.value.required_if // {}) | to_entries[]
          | "R" + strenv(LP_SEP) + $f + strenv(LP_SEP) + .key + strenv(LP_SEP) + (.value | tostring) ),
      ( .operations | to_entries[] | .key as $o | .value.fields[]
          | "P" + strenv(LP_SEP) + $o + strenv(LP_SEP) + . ),
      ( .operations | to_entries[] | .key as $o | (.value.required // [])[]
          | "U" + strenv(LP_SEP) + $o + strenv(LP_SEP) + . ),
      ( .operations | to_entries[] | .key as $o | (.value.sets // {}) | to_entries[]
          | "T" + strenv(LP_SEP) + $o + strenv(LP_SEP) + .key + strenv(LP_SEP) + (.value | tostring) )
    ' "$_LP_SCHEMA" 2>&1)
    rc=$?

    if [ "$rc" -ne 0 ]; then
        _lp_die "yq could not read $_LP_SCHEMA (exit $rc).
  yq version: $(yq --version 2>&1 | head -1)
  yq said:    $(printf '%s' "$raw" | head -3)"
    fi

    while IFS="$LP_SEP" read -r kind a b c; do
        # Field names reach `eval` below as part of a variable name, so they are
        # checked here rather than trusted. Operation names may contain dots and
        # are folded; that happens once, not per line.
        case "$kind" in
            N|F|O|D|S|R)
                case "$a" in
                    [a-z]*) ;;
                    *) _lp_die "Field name '$a' must match ^[a-z][a-z0-9_]*\$." ;;
                esac
                ;;
        esac
        case "$kind" in
            N) _lp_add "FIELDS" "$a" ;;                         # field name
            Q) _lp_add "OPS" "$a" ;;                            # operation name
            F) _lp_put "F_${a}__$b" "$c" ;;                     # field scalar prop
            O) _lp_add "L_${a}__options" "$b" ;;
            D) _lp_add "L_${a}__deny_prefix" "$b" ;;
            S) _lp_add "L_${a}__show_if" "$b=$c" ;;
            R) _lp_add "L_${a}__required_if" "$b=$c" ;;
            P) _lp_add "OF_$(_lp_key "$a")" "$b" ;;             # operation field
            U) _lp_add "OR_$(_lp_key "$a")" "$b" ;;             # required by this operation
            T) _lp_add "OT_$(_lp_key "$a")" "$b=$c" ;;          # operation constant
        esac
    done <<EOF
$raw
EOF

    # Never fail silently here. An empty schema means every rule is absent, so
    # the shim would wave through anything -- the exact failure this whole gate
    # exists to prevent. Say what was actually seen.
    _lp_val_into FIELDS _probe
    if [ -z "$_probe" ]; then
        _lp_die "Read $_LP_SCHEMA but parsed no fields from it.
  yq version:   $(yq --version 2>&1 | head -1)
  yq returned:  $(printf '%s\n' "$raw" | grep -c . ) line(s)
  first line:   $(printf '%s' "$raw" | head -1 | cat -v)
  expected:     N^Irequest_id      (^I is a tab)

  If the ^I is missing above, this yq build is not producing the field
  separator and the parser cannot split the line. If the line is missing
  entirely, this yq build does not support to_entries/del on this document."
    fi
}

# ---------------------------------------------------------------------------
# One more for the payload.
# ---------------------------------------------------------------------------
_lp_load_payload() {
    local ptype k v raw rc keycount _parsed

    ptype=$(printf '%s' "$_LP_PAYLOAD" | yq -p json -r 'type' 2>/dev/null) || ptype=""
    [ "$ptype" = "!!map" ] || _lp_die "REQUEST_PAYLOAD must be a JSON object. Parsed as: ${ptype:-invalid JSON}"

    # strenv(LP_SEP), not "\t", for the same reason as _lp_load_schema: some yq
    # builds emit the literal rather than a tab, and the failure is silent. Here
    # it would be worse than silent -- every supplied field would look absent,
    # so a complete request would be rejected for "request_id is required".
    LP_SEP=$(printf '\t')
    export LP_SEP

    raw=$(printf '%s' "$_LP_PAYLOAD" | yq -p json -r 'to_entries[] | .key + strenv(LP_SEP) + (.value | tostring)' 2>&1)
    rc=$?
    [ "$rc" -eq 0 ] || _lp_die "yq could not read REQUEST_PAYLOAD (exit $rc).
  yq version: $(yq --version 2>&1 | head -1)
  yq said:    $(printf '%s' "$raw" | head -3)"

    while IFS="$LP_SEP" read -r k v; do
        [ -n "$k" ] || continue
        # A value containing a newline or tab would split this line. No field in
        # the schema has any use for one, so it is rejected rather than guessed
        # at -- a silently truncated value is worse than a failed pipeline.
        printf '%s' "$k" | grep -q '^[a-z][a-z0-9_]*$' \
            || _lp_die "REQUEST_PAYLOAD keys must match ^[a-z][a-z0-9_]*\$ and values must not contain tabs or newlines (near '$k')."
        _lp_add "PKEYS" "$k"
        _lp_put "PV_$(_lp_key "$k")" "$v"
    done <<EOF
$raw
EOF

    # A non-empty payload that yields no keys means the separator did not survive.
    # Without this the request fails later as "everything is missing", which
    # points at the operator rather than at the real cause.
    keycount=$(printf '%s' "$_LP_PAYLOAD" | yq -p json -r 'to_entries | length' 2>/dev/null || echo 0)
    _lp_val_into PKEYS _parsed
    if [ "${keycount:-0}" -gt 0 ] && [ -z "$_parsed" ]; then
        _lp_die "REQUEST_PAYLOAD has $keycount key(s) but none could be parsed.
  yq version: $(yq --version 2>&1 | head -1)
  first line: $(printf '%s' "$raw" | head -1 | cat -v)
  expected:   request_id^IREQ0001      (^I is a tab)"
    fi
}

_lp_has_line() { printf '%s\n' "$1" | grep -qxF "$2"; }

# Resolved values live in _LPV_<field>; flags in _LPF_<field>_<flag>.
_lp_set()      { eval "_LPV_$1=\$2"; }
_lp_set_flag() { eval "_LPF_$1_$2=\$3"; }

# Does `show_if` / `required_if` hold against currently resolved values?
# An absent condition holds vacuously.
_lp_conditions_hold() {
    local pairs pair key expected actual
    _lp_list_into "$1" "$2" pairs
    [ -n "$pairs" ] || return 0
    while IFS= read -r pair; do
        [ -n "$pair" ] || continue
        key="${pair%%=*}"
        expected="${pair#*=}"
        _lp_get_into "$key" actual
        [ "$actual" = "$expected" ] || return 1
    done <<EOF
$pairs
EOF
    return 0
}

# Validate a datetime in the format the operator actually supplies, then the
# component ranges the shape still allows -- an impossible month has to fail
# here, with a clear message, rather than somewhere downstream.
_lp_check_datetime() {
    local name="$1" v="$2" fmt mo d h mi s
    fmt=$(_lp_datetime_format "$name")
    case "$fmt" in
        "DD/MM/YYYY HH:mm:ss")
            printf '%s' "$v" | grep -qE '^[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}$' \
                || _lp_die "'$name' must be DD/MM/YYYY HH:MM:SS exactly as MyITSM shows it, got '$v'."
            d=$(printf  '%s' "$v" | cut -c1-2);  mo=$(printf '%s' "$v" | cut -c4-5)
            h=$(printf  '%s' "$v" | cut -c12-13); mi=$(printf '%s' "$v" | cut -c15-16)
            s=$(printf  '%s' "$v" | cut -c18-19)
            ;;
        "YYYY-MM-DDTHH:mm:ss")
            printf '%s' "$v" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$' \
                || _lp_die "'$name' must be ISO 8601 (YYYY-MM-DDTHH:MM:SS), got '$v'."
            mo=$(printf '%s' "$v" | cut -c6-7);  d=$(printf '%s' "$v" | cut -c9-10)
            h=$(printf  '%s' "$v" | cut -c12-13); mi=$(printf '%s' "$v" | cut -c15-16)
            s=$(printf  '%s' "$v" | cut -c18-19)
            ;;
        *) _lp_die "Unsupported input_format '$fmt' on field '$name'." ;;
    esac
    # 10# forces base 10 so a leading zero is not read as octal.
    [ $((10#$mo)) -ge 1 ] && [ $((10#$mo)) -le 12 ] || _lp_die "'$name' has an invalid month: $mo"
    [ $((10#$d))  -ge 1 ] && [ $((10#$d))  -le 31 ] || _lp_die "'$name' has an invalid day: $d"
    [ $((10#$h))  -le 23 ] || _lp_die "'$name' has an invalid hour: $h"
    [ $((10#$mi)) -le 59 ] || _lp_die "'$name' has an invalid minute: $mi"
    [ $((10#$s))  -le 59 ] || _lp_die "'$name' has an invalid second: $s"
}

_lp_datetime_format() {
    local fmt; _lp_prop_into "$1" input_format fmt
    [ -n "$fmt" ] || fmt="YYYY-MM-DDTHH:mm:ss"
    printf '%s' "$fmt"
}

# Reassemble the supplied datetime into the ISO 8601 the scripts and the stored
# metadata use. Pure string slicing: no `date`, so no timezone or locale
# surprises and no GNU-vs-BSD divergence.
_lp_to_iso() {
    local v="$2"
    [ -n "$v" ] || { printf '%s' "$v"; return; }
    case "$(_lp_datetime_format "$1")" in
        "DD/MM/YYYY HH:mm:ss")
            printf '%s-%s-%sT%s' \
                "$(printf '%s' "$v" | cut -c7-10)" \
                "$(printf '%s' "$v" | cut -c4-5)" \
                "$(printf '%s' "$v" | cut -c1-2)" \
                "$(printf '%s' "$v" | cut -c12-19)"
            ;;
        *) printf '%s' "$v" ;;
    esac
}

load_payload() {
    local all_fields all_ops op_fields op_key name nkey value ftype
    local present default absent pattern deny p pairs key
    local changed round is_required

    # ---- 0. preconditions ------------------------------------------------
    command -v yq >/dev/null 2>&1 || _lp_die "yq is not on PATH."
    [ -f "$_LP_SCHEMA" ] || _lp_die "Schema not found at '$_LP_SCHEMA'. Set REQUEST_SCHEMA to override."
    [ -n "${OPERATION:-}" ] || _lp_die "OPERATION is not set."

    _LP_PAYLOAD="${REQUEST_PAYLOAD:-}"
    [ -n "$_LP_PAYLOAD" ] || _LP_PAYLOAD="{}"

    echo "==========================================================================="
    echo "                           Loading Request Payload                         "
    echo "==========================================================================="

    _lp_load_schema
    _lp_load_payload

    _lp_val_into FIELDS all_fields
    _lp_val_into OPS all_ops

    # ---- 1. the operation must be declared -------------------------------
    _lp_has_line "$all_ops" "$OPERATION" \
        || _lp_die "Unknown OPERATION '$OPERATION'. Declared: $(printf '%s' "$all_ops" | tr '\n' ' ')"

    op_key=$(_lp_key "$OPERATION")
    _lp_val_into "OF_$op_key" op_fields
    _lp_val_into "OR_$op_key" op_required

    _lp_val_into PKEYS payload_keys

    # ---- 2. reject payload keys this operation does not accept -----------
    # A typo'd key would otherwise be silently ignored and the field would
    # quietly take its default -- a failure the old form could not have, because
    # GitLab rejected unknown inputs itself.
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        if ! _lp_has_line "$op_fields" "$key"; then
            if _lp_has_line "$all_fields" "$key"; then
                _lp_die "Field '$key' is not accepted by operation '$OPERATION'."
            fi
            _lp_die "Unknown field '$key' in REQUEST_PAYLOAD. Not declared in $_LP_SCHEMA."
        fi
    done <<EOF
$payload_keys
EOF

    # ---- 3. resolve every declared field ---------------------------------
    # Every field in the schema is resolved, not only the ones this operation
    # offers, so no sourced script ever reads an unset INPUT_*. Fields outside
    # the operation take their default and are never required.
    while IFS= read -r name; do
        [ -n "$name" ] || continue

        _lp_prop_into "$name" default value
        present="false"

        if _lp_has_line "$op_fields" "$name" && _lp_has_line "$payload_keys" "$name"; then
            present="true"
            _lp_val_into "PV_$name" value
        fi

        _lp_prop_into "$name" normalise norm
        case "$norm" in
            lower) value=$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]') ;;
            upper) value=$(printf '%s' "$value" | tr '[:lower:]' '[:upper:]') ;;
        esac

        _lp_set "$name" "$value"
        _lp_set_flag "$name" present "$present"
        _lp_set_flag "$name" hidden "false"
    done <<EOF
$all_fields
EOF

    # ---- 4. apply show_if, to a fixed point ------------------------------
    # Iterated because conditions chain: registry_username is shown only when
    # registry_auth is true, and registry_auth is itself hidden for the internal
    # replication types. A single pass would leave the inner field visible.
    round=0
    changed="true"
    while [ "$changed" = "true" ]; do
        changed="false"
        round=$((round + 1))
        [ "$round" -le 10 ] || _lp_die "show_if conditions did not settle after 10 rounds; check for a cycle in $_LP_SCHEMA."

        while IFS= read -r name; do
            [ -n "$name" ] || continue
            _lp_flag_into "$name" hidden hidden
            [ "$hidden" = "false" ] || continue
            _lp_conditions_hold "$name" show_if && continue

            _lp_prop_into "$name" absent_value absent
            [ -n "$absent" ] || _lp_prop_into "$name" default absent
            _lp_set "$name" "$absent"
            _lp_set_flag "$name" hidden "true"
            changed="true"
        done <<EOF
$all_fields
EOF
    done

    # ---- 5. validate -----------------------------------------------------
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        _lp_has_line "$op_fields" "$name" || continue
        _lp_flag_into "$name" hidden hidden
        [ "$hidden" = "false" ] || continue

        _lp_get_into "$name" value
        _lp_flag_into "$name" present present
        _lp_prop_into "$name" type ftype

        # -- required / required_if / operation-level required --
        is_required="false"
        _lp_prop_into "$name" required req_prop
        [ "$req_prop" = "true" ] && is_required="true"
        # A field can be optional for one operation and required for another:
        # a namespace name is optional when creating and mandatory when updating.
        _lp_has_line "$op_required" "$name" && is_required="true"
        if [ "$is_required" = "false" ]; then
            _lp_list_into "$name" required_if req_cond
            if [ -n "$req_cond" ]; then
                _lp_conditions_hold "$name" required_if && is_required="true"
            fi
        fi

        # `required` means the operator supplied it, not merely that the value
        # ended up non-empty. Those differ whenever a field has a default, and
        # the difference is load-bearing: gpu_tier defaults to the literal
        # "None" that the scaffold script demands when GPU is off, so a
        # non-emptiness check let "GPU on, no tier chosen" through -- the field
        # satisfied its own requirement with the sentinel for absence.
        #
        # A field that is genuinely required therefore ignores its default. The
        # default on a required field is a form pre-selection, nothing more.
        if [ "$is_required" = "true" ]; then
            [ "$present" = "true" ] \
                || _lp_die "'$name' is required for operation '$OPERATION' and was not supplied."
            [ -n "$value" ] \
                || _lp_die "'$name' is required for operation '$OPERATION' and must not be empty."
        fi

        [ -n "$value" ] || continue   # nothing further to check on an empty value

        # -- type --
        case "$ftype" in
            boolean)
                case "$value" in
                    true|false) ;;
                    *) _lp_die "'$name' must be true or false, got '$value'." ;;
                esac
                ;;
            integer)
                printf '%s' "$value" | grep -qE '^-?[0-9]+$' || _lp_die "'$name' must be an integer, got '$value'."
                ;;
            datetime)
                _lp_check_datetime "$name" "$value"
                ;;
            email)
                printf '%s' "$value" | grep -qE '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' \
                    || _lp_die "'$name' is not a valid email address: '$value'."
                ;;
            url)
                printf '%s' "$value" | grep -qE '^https?://' || _lp_die "'$name' must be a URL, got '$value'."
                ;;
            enum)
                _lp_list_into "$name" options opts
                _lp_prop_into "$name" absent_value opt_absent
                _lp_prop_into "$name" default opt_default
                if ! _lp_has_line "$opts" "$value" \
                   && [ "$value" != "$opt_absent" ] \
                   && [ "$value" != "$opt_default" ]; then
                    _lp_die "'$name' must be one of: $(printf '%s' "$opts" | tr '\n' ' ')-- got '$value'."
                fi
                ;;
        esac

        # -- pattern --
        _lp_prop_into "$name" pattern pattern
        if [ -n "$pattern" ]; then
            printf '%s' "$value" | grep -qE "$pattern" \
                || _lp_die "'$name' does not match the required format ($pattern): '$value'."
        fi

        # -- denied prefixes --
        _lp_list_into "$name" deny_prefix deny
        if [ -n "$deny" ]; then
            while IFS= read -r p; do
                [ -n "$p" ] || continue
                case "$value" in
                    "$p"*) _lp_die "'$name' may not start with '$p' — that prefix is reserved." ;;
                esac
            done <<EOF
$deny
EOF
        fi
    done <<EOF
$all_fields
EOF

    # ---- 6. export -------------------------------------------------------
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        _lp_prop_into "$name" env key
        [ -n "$key" ] || _lp_die "Field '$name' has no 'env' in $_LP_SCHEMA."

        _lp_get_into "$name" value
        # A datetime is supplied in whatever format the operator can paste and
        # exported as ISO 8601, so the scripts never see the other one.
        _lp_prop_into "$name" type ftype
        [ "$ftype" = "datetime" ] && value=$(_lp_to_iso "$name" "$value")
        export "$key=$value"
    done <<EOF
$all_fields
EOF

    # ---- 7. operation constants ------------------------------------------
    # Values derived from the operation rather than supplied by the operator.
    # This is what retired INPUT_CREATE_CSO / INPUT_DECOMMISSION /
    # INPUT_DECOMMISSION_CSO as things a human could set inconsistently.
    _lp_val_into "OT_$op_key" pairs
    if [ -n "$pairs" ]; then
        while IFS= read -r p; do
            [ -n "$p" ] || continue
            export "${p%%=*}=${p#*=}"
        done <<EOF
$pairs
EOF
    fi

    _lp_summary "$op_fields" "$all_fields"
}

# Echo what was resolved. With 25 labelled form fields gone, this log is the
# only place an operator or a reviewer can see what the run actually received.
_lp_summary() {
    local op_fields="$1" all_fields="$2" name env_name value shown hidden
    echo "-> Operation: $OPERATION"
    echo "---------------------------------------------------------------------------"
    printf "   %-30s %s\n" "FIELD" "VALUE"
    echo "---------------------------------------------------------------------------"
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        _lp_has_line "$op_fields" "$name" || continue
        _lp_prop_into "$name" env env_name
        eval "value=\${$env_name}"
        shown="$value"
        [ -n "$shown" ] || shown="<empty>"
        _lp_flag_into "$name" hidden hidden
        [ "$hidden" = "true" ] && shown="$shown  (not applicable)"
        printf "   %-30s %s\n" "$name" "$shown"
    done <<EOF
$all_fields
EOF
    echo "---------------------------------------------------------------------------"
}

load_payload
