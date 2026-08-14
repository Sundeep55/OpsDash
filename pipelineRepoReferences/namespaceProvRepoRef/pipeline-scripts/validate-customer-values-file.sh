#!/bin/bash
set -e

# --- Helper Functions ---
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

function validate_customer_values_file_input() {
    log_info "Security Check: Validating Harbor Robot Account Permissions .."
    
    CHANGES=$(git diff --name-only $CI_MERGE_REQUEST_DIFF_BASE_SHA...$CI_COMMIT_SHA | grep -E '^[^/]+/[^/]+/[^/]+/values\.yaml$' || true)

    if [ -z "$CHANGES" ]; then
        log_info "No tenant-specific values.yaml files were modified. Skipping check."
        return 0
    fi

    VIOLATION_FOUND=0

    for TARGET_FILE in $CHANGES; do
        echo "------------------------------------------------------------"
        
        LIFECYCLE=$(yq '.dcs-namespace-provisioner.requiredLabels["dcs.airbus.com/lifecycle"]' "$TARGET_FILE")
        log_info "Checking: $TARGET_FILE (Lifecycle: $LIFECYCLE)"
        
        if [[ "$LIFECYCLE" == "prod" ]]; then
            set +e
            INVALID_PUSH_FOUND=$(yq -e '.dcs-namespace-provisioner.harborRobotAccounts.robotAccounts[] | select(.default == false) | .permissions[] | select(.action == "push")' "$TARGET_FILE" 2>/dev/null)
            set -e

            if [[ -n "$INVALID_PUSH_FOUND" ]]; then
                log_error "🚨 SECURITY VIOLATION: Forbidden 'push' permission found in $TARGET_FILE"
                # Show the specific line to the developer
                grep -n -B 1 -E "action: [\"']?push[\"']?" "$TARGET_FILE" | grep -v "^--"
                echo ""
                VIOLATION_FOUND=1
            else
                log_info "$TARGET_FILE is clean."
            fi
        else
            log_info "Skipping strict push check (Non-prod lifecycle: $LIFECYCLE)."
        fi
    done

    if [ "$VIOLATION_FOUND" -eq 1 ]; then
        echo "============================================================"
        log_error "FAILURE: One or more files contain forbidden permissions."
        log_error "Custom Robot Accounts in PROD cannot have PUSH access."
        echo "============================================================"
        exit 1
    fi

    log_info "Success: All modified files passed the security check."
}

validate_customer_values_file_input