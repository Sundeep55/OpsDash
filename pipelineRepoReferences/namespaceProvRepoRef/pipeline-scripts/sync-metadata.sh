#!/bin/bash
set -e

# --- Helper Functions ---
log_info() {
    echo "-> $1"
}

log_error() {
    echo "ERROR: $1"
}

function run_sync() {
    CLUSTER_DIR="${INPUT_TARGET_CLUSTER}"
    
    if [ ! -d "$CLUSTER_DIR" ]; then
        log_error "Target cluster directory '$CLUSTER_DIR' not found."
        exit 1
    fi

    log_info "Starting Metadata Sync scan on: $CLUSTER_DIR"
    
    # Git Setup
    git config --global user.email "${GITLAB_USER_EMAIL}"
    git config --global user.name "${GITLAB_USER_NAME}"
    NEW_BRANCH_NAME="chore/sync-metadata-$(date +%Y%m%d-%H%M%S)"
    git checkout -b "$NEW_BRANCH_NAME"

    CHANGES_DETECTED=false

    # Loop through all directories in the cluster folder (Tenants)
    for tenant_path in "$CLUSTER_DIR"/*; do
        if [ ! -d "$tenant_path" ]; then continue; fi
        
        tenant_name=$(basename "$tenant_path")
        
        # Skip special folders
        if [[ "$tenant_name" == "decommissioned_tenants" ]]; then continue; fi

        metadata_file="$tenant_path/tenant-metadata.yaml"

        # Check if metadata exists
        if [ -f "$metadata_file" ]; then
            log_info "[SKIP] $tenant_name: Metadata already exists."
            continue
        fi

        log_info "[SYNC] $tenant_name: Creating missing metadata file..."
        CHANGES_DETECTED=true
        
        # Export for yq
        export tenant_name

        # Create base file
        yq -n '
            .tenant_name = strenv(tenant_name) |
            .requester = "" |
            .tenant_request_ticket = "" |
            .cost_center = "" |
            .requested_timestamp = "" |
            .provision_timestamp = "" |
            .active_namespaces = []
        ' > "$metadata_file"

        # Scan for namespaces inside the tenant
        for ns_path in "$tenant_path"/*; do
            if [ ! -d "$ns_path" ]; then continue; fi
            ns_name=$(basename "$ns_path")

            # Filter logic: A namespace must be a folder and contain values.yaml
            # Also exclude known non-namespace folders
            if [[ "$ns_name" == "decommissioned_namespaces" ]]; then continue; fi
            
            if [ -f "$ns_path/values.yaml" ]; then
                log_info "    -> Found namespace: $ns_name"
                export ns_name
                
                # Append namespace to list
                yq -i '
                    .active_namespaces += [{
                        "name": strenv(ns_name),
                        "requester": "",
                        "namespace_request_ticket": "",
                        "requested_timestamp": "",
                        "provision_timestamp": ""
                    }]
                ' "$metadata_file"
            fi
        done
    done

    if [ "$CHANGES_DETECTED" = "true" ]; then
        log_info "Commiting and pushing changes..."
        git add "$CLUSTER_DIR"
        git commit -m "chore: Auto-generate missing tenant metadata files"
        git push "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME"
        
        echo ""
        echo "---------------------------------------------------------------------------"
        echo "| SYNC COMPLETE.                                                          |"
        echo "| Branch '$NEW_BRANCH_NAME' has been pushed.                              |"
        echo "| Please merge and fill the blank fields manually.                        |"
        echo "---------------------------------------------------------------------------"
    else
        log_info "No missing metadata files found. Nothing to do."
    fi
}

# --- Main Execution ---
if [[ "${DEBUG}" == "true" ]]; then
    set -x
fi

run_sync
