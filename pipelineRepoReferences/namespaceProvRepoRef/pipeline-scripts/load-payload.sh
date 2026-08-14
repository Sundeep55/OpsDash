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

# Shell variable names are built from field and operation names, so anything
# that is not [A-Za-z0-9_] is folded away first.
_lp_key() { local s="$1"; printf '%s' "${s//[!a-zA-Z0-9_]/_}"; }

_lp_put()  { eval "_LPD_$1=\$2"; }
_lp_val()  { eval "printf '%s' \"\${_LPD_$1}\""; }
_lp_add()  {
    local cur; eval "cur=\${_LPD_$1}"
    if [ -z "$cur" ]; then eval "_LPD_$1=\$2"; else eval "_LPD_$1=\"\$cur\$_LP_NL\$2\""; fi
}

# Scalar property of a field, e.g. `_lp_prop gpu_tier type` -> enum
_lp_prop() { _lp_val "F_$(_lp_key "$1")__$2"; }
# Multi-valued property: options, deny_prefix, show_if, required_if
_lp_list() { _lp_val "L_$(_lp_key "$1")__$2"; }

# ---------------------------------------------------------------------------
# One yq call. Emits a flat, tab-separated description of everything below.
#
# Scalars are selected as "not a map and not a seq" rather than by listing the
# scalar tags. An `or` chain -- select(.value | tag == "!!str" or tag ==
# "!!bool") -- silently drops the booleans in yq v4, even with explicit
# parentheses. That made every `required: true` invisible, so nothing was ever
# required and the shim accepted payloads with mandatory fields missing. The
# negative form is both correct and future-proof against a schema growing a
# float or a null.
# ---------------------------------------------------------------------------
_lp_load_schema() {
    local line kind a b c
    while IFS="$(printf '\t')" read -r kind a b c; do
        case "$kind" in
            N) _lp_add "FIELDS" "$a" ;;                         # field name
            Q) _lp_add "OPS" "$a" ;;                            # operation name
            F) _lp_put "F_$(_lp_key "$a")__$b" "$c" ;;          # field scalar prop
            O) _lp_add "L_$(_lp_key "$a")__options" "$b" ;;
            D) _lp_add "L_$(_lp_key "$a")__deny_prefix" "$b" ;;
            S) _lp_add "L_$(_lp_key "$a")__show_if" "$b=$c" ;;
            R) _lp_add "L_$(_lp_key "$a")__required_if" "$b=$c" ;;
            P) _lp_add "OF_$(_lp_key "$a")" "$b" ;;             # operation field
            T) _lp_add "OT_$(_lp_key "$a")" "$b=$c" ;;          # operation constant
        esac
    done <<EOF
$(yq -r '
  ( .fields | keys | .[] | "N\t" + . ),
  ( .operations | keys | .[] | "Q\t" + . ),
  ( .fields | to_entries[] | .key as $f | .value | to_entries[]
      | select(.value | (tag != "!!map") and (tag != "!!seq"))
      | "F\t" + $f + "\t" + .key + "\t" + (.value | tostring) ),
  ( .fields | to_entries[] | .key as $f | (.value.options     // [])[] | "O\t" + $f + "\t" + . ),
  ( .fields | to_entries[] | .key as $f | (.value.deny_prefix // [])[] | "D\t" + $f + "\t" + . ),
  ( .fields | to_entries[] | .key as $f | (.value.show_if     // {}) | to_entries[] | "S\t" + $f + "\t" + .key + "\t" + (.value|tostring) ),
  ( .fields | to_entries[] | .key as $f | (.value.required_if // {}) | to_entries[] | "R\t" + $f + "\t" + .key + "\t" + (.value|tostring) ),
  ( .operations | to_entries[] | .key as $o | .value.fields[] | "P\t" + $o + "\t" + . ),
  ( .operations | to_entries[] | .key as $o | (.value.sets // {}) | to_entries[] | "T\t" + $o + "\t" + .key + "\t" + (.value|tostring) )
' "$_LP_SCHEMA" 2>/dev/null)
EOF
    [ -n "$(_lp_val FIELDS)" ] || _lp_die "Could not read any fields from $_LP_SCHEMA."
}

# ---------------------------------------------------------------------------
# One more for the payload.
# ---------------------------------------------------------------------------
_lp_load_payload() {
    local ptype k v
    ptype=$(printf '%s' "$_LP_PAYLOAD" | yq -p json -r 'type' 2>/dev/null) || ptype=""
    [ "$ptype" = "!!map" ] || _lp_die "REQUEST_PAYLOAD must be a JSON object. Parsed as: ${ptype:-invalid JSON}"

    while IFS="$(printf '\t')" read -r k v; do
        [ -n "$k" ] || continue
        # A value containing a newline or tab would split this line. No field in
        # the schema has any use for one, so it is rejected rather than guessed
        # at -- a silently truncated value is worse than a failed pipeline.
        printf '%s' "$k" | grep -q '^[a-z][a-z0-9_]*$' \
            || _lp_die "REQUEST_PAYLOAD keys must match ^[a-z][a-z0-9_]*\$ and values must not contain tabs or newlines (near '$k')."
        _lp_add "PKEYS" "$k"
        _lp_put "PV_$(_lp_key "$k")" "$v"
    done <<EOF
$(printf '%s' "$_LP_PAYLOAD" | yq -p json -r 'to_entries[] | .key + "\t" + (.value | tostring)' 2>/dev/null)
EOF
}

_lp_has_line() { printf '%s\n' "$1" | grep -qxF "$2"; }

# Resolved values live in _LPV_<field>; flags in _LPF_<field>_<flag>.
_lp_set()      { eval "_LPV_$1=\$2"; }
_lp_get()      { eval "printf '%s' \"\$_LPV_$1\""; }
_lp_set_flag() { eval "_LPF_$1_$2=\$3"; }
_lp_get_flag() { eval "printf '%s' \"\$_LPF_$1_$2\""; }

# Does `show_if` / `required_if` hold against currently resolved values?
# An absent condition holds vacuously.
_lp_conditions_hold() {
    local pairs pair key expected actual
    pairs=$(_lp_list "$1" "$2")
    [ -n "$pairs" ] || return 0
    while IFS= read -r pair; do
        [ -n "$pair" ] || continue
        key="${pair%%=*}"
        expected="${pair#*=}"
        actual=$(_lp_get "$(_lp_key "$key")")
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
    local fmt; fmt=$(_lp_prop "$1" input_format)
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

    all_fields=$(_lp_val FIELDS)
    all_ops=$(_lp_val OPS)

    # ---- 1. the operation must be declared -------------------------------
    _lp_has_line "$all_ops" "$OPERATION" \
        || _lp_die "Unknown OPERATION '$OPERATION'. Declared: $(printf '%s' "$all_ops" | tr '\n' ' ')"

    op_key=$(_lp_key "$OPERATION")
    op_fields=$(_lp_val "OF_$op_key")

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
$(_lp_val PKEYS)
EOF

    # ---- 3. resolve every declared field ---------------------------------
    # Every field in the schema is resolved, not only the ones this operation
    # offers, so no sourced script ever reads an unset INPUT_*. Fields outside
    # the operation take their default and are never required.
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        # Field names reach `eval` below (only ever as part of a variable name,
        # never as a value), so they are checked rather than trusted.
        printf '%s' "$name" | grep -q '^[a-z][a-z0-9_]*$' \
            || _lp_die "Field name '$name' must match ^[a-z][a-z0-9_]*\$."
        nkey=$(_lp_key "$name")

        default=$(_lp_prop "$name" default)
        present="false"
        value="$default"

        if _lp_has_line "$op_fields" "$name" && _lp_has_line "$(_lp_val PKEYS)" "$name"; then
            present="true"
            value=$(_lp_val "PV_$nkey")
        fi

        case "$(_lp_prop "$name" normalise)" in
            lower) value=$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]') ;;
            upper) value=$(printf '%s' "$value" | tr '[:lower:]' '[:upper:]') ;;
        esac

        _lp_set "$nkey" "$value"
        _lp_set_flag "$nkey" present "$present"
        _lp_set_flag "$nkey" hidden "false"
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
            nkey=$(_lp_key "$name")
            [ "$(_lp_get_flag "$nkey" hidden)" = "false" ] || continue
            _lp_conditions_hold "$name" show_if && continue

            absent=$(_lp_prop "$name" absent_value)
            [ -n "$absent" ] || absent=$(_lp_prop "$name" default)
            _lp_set "$nkey" "$absent"
            _lp_set_flag "$nkey" hidden "true"
            changed="true"
        done <<EOF
$all_fields
EOF
    done

    # ---- 5. validate -----------------------------------------------------
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        _lp_has_line "$op_fields" "$name" || continue
        nkey=$(_lp_key "$name")
        [ "$(_lp_get_flag "$nkey" hidden)" = "false" ] || continue

        value=$(_lp_get "$nkey")
        present=$(_lp_get_flag "$nkey" present)
        ftype=$(_lp_prop "$name" type)

        # -- required / required_if --
        is_required="false"
        [ "$(_lp_prop "$name" required)" = "true" ] && is_required="true"
        if [ "$is_required" = "false" ] && [ -n "$(_lp_list "$name" required_if)" ]; then
            _lp_conditions_hold "$name" required_if && is_required="true"
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
            [ "$present" = "true" ] || {
                if [ "$(_lp_prop "$name" allow_empty)" = "true" ]; then
                    _lp_die "'$name' must be supplied. Send \"\" if that is intentional (e.g. a non-billable cost centre)."
                fi
                _lp_die "'$name' is required for operation '$OPERATION' and was not supplied."
            }
            # Present but blank is only acceptable where the schema says so --
            # an empty cost centre means non-billable and is a real answer.
            if [ "$(_lp_prop "$name" allow_empty)" != "true" ]; then
                [ -n "$value" ] || _lp_die "'$name' is required for operation '$OPERATION' and must not be empty."
            fi
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
                if ! _lp_has_line "$(_lp_list "$name" options)" "$value" \
                   && [ "$value" != "$(_lp_prop "$name" absent_value)" ] \
                   && [ "$value" != "$(_lp_prop "$name" default)" ]; then
                    _lp_die "'$name' must be one of: $(_lp_list "$name" options | tr '\n' ' ')-- got '$value'."
                fi
                ;;
        esac

        # -- pattern --
        pattern=$(_lp_prop "$name" pattern)
        if [ -n "$pattern" ]; then
            printf '%s' "$value" | grep -qE "$pattern" \
                || _lp_die "'$name' does not match the required format ($pattern): '$value'."
        fi

        # -- denied prefixes --
        deny=$(_lp_list "$name" deny_prefix)
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
        nkey=$(_lp_key "$name")
        key=$(_lp_prop "$name" env)
        [ -n "$key" ] || _lp_die "Field '$name' has no 'env' in $_LP_SCHEMA."

        value=$(_lp_get "$nkey")
        # A datetime is supplied in whatever format the operator can paste and
        # exported as ISO 8601, so the scripts never see the other one.
        [ "$(_lp_prop "$name" type)" = "datetime" ] && value=$(_lp_to_iso "$name" "$value")
        export "$key=$value"
    done <<EOF
$all_fields
EOF

    # ---- 7. operation constants ------------------------------------------
    # Values derived from the operation rather than supplied by the operator.
    # This is what retired INPUT_CREATE_CSO / INPUT_DECOMMISSION /
    # INPUT_DECOMMISSION_CSO as things a human could set inconsistently.
    pairs=$(_lp_val "OT_$op_key")
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
    local op_fields="$1" all_fields="$2" name nkey env_name value shown
    echo "-> Operation: $OPERATION"
    echo "---------------------------------------------------------------------------"
    printf "   %-30s %s\n" "FIELD" "VALUE"
    echo "---------------------------------------------------------------------------"
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        _lp_has_line "$op_fields" "$name" || continue
        nkey=$(_lp_key "$name")
        env_name=$(_lp_prop "$name" env)
        eval "value=\${$env_name}"
        shown="$value"
        [ -n "$shown" ] || shown="<empty>"
        [ "$(_lp_get_flag "$nkey" hidden)" = "true" ] && shown="$shown  (not applicable)"
        printf "   %-30s %s\n" "$name" "$shown"
    done <<EOF
$all_fields
EOF
    echo "---------------------------------------------------------------------------"
}

load_payload
