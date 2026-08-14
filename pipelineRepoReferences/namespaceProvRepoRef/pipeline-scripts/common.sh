#!/bin/bash
# =============================================================================
# common.sh — shared helpers, sourced by every pipeline script.
#
# These four functions were duplicated verbatim in scaffold.sh, decommission.sh
# and the registry-mirror script back when the mirror lived in its own repo.
# One copy now.
# =============================================================================

log_info() {
    if [[ "${DEBUG}" == "true" ]]; then
        echo -e "[$(date +'%H:%M:%S')] -> $1"
    else
        echo "-> $1"
    fi
}

log_error() {
    if [[ "${DEBUG}" == "true" ]]; then
        echo -e "[$(date +'%H:%M:%S')] ERROR: $1"
    else
        echo "ERROR: $1"
    fi
}

banner() {
    echo "==========================================================================="
    printf "%*s\n" $(( (75 + ${#1}) / 2 )) "$1"
    echo "==========================================================================="
}

# Called by each script once its own `source` lines are done.
enable_debug_if_requested() {
    if [[ "${DEBUG}" == "true" ]]; then
        banner "*** Debug Enabled ***"
        set -x
    fi
}
