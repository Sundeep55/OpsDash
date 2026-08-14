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

function validate_inputs() {
    echo "==========================================================================="
    echo "                            Validate Inputs                                "
    echo "==========================================================================="
    log_info "Validating inputs..."

    # Check Email
    case "$INPUT_REQUESTER_EMAIL" in
      "projectowner@zzz.com" | \
      "user@example.com" | \
      "projectowneruser01@zzz.com" | \
      "projectowneruser02@zzz.com" | \
      "projectuser01@zzz.com" | \
      "projectuser02@zzz.com")
          log_error "'REQUESTER_EMAIL' was left as default ($INPUT_REQUESTER_EMAIL). Please provide the real requester's email."
          exit 1
          ;;
      *)
          ;;
    esac

    # Check Request ID Default
    [[ "$INPUT_REQUEST_ID" == "REQ00000000000XX" ]] && { log_error "Invalid Request ID (Default detected)."; exit 1; }

    # Check Cost Center Code
    if [[ "$INPUT_COST_CENTER" == "XX/YY0000-00000" ]]; then
        log_error "Cost Center code is set to default."
        log_error "Please enter a valid code OR clear the field for Non-Billable tenants."
        exit 1
    fi
    
    if [[ -z "$INPUT_COST_CENTER" ]]; then
        log_info "Cost Center code is empty. Proceeding as Non-Billable tenant."
    fi

    # Check Timestamp Default
    [[ "$INPUT_REQUESTED_TIMESTAMP" == "01/04/2026 13:47:48" ]] && { log_error "Invalid Timestamp (Default detected)."; exit 1; }

    # Validate Timestamp Regex (Expected: DD/MM/YYYY HH:MM:SS)
    if [[ ! "$INPUT_REQUESTED_TIMESTAMP" =~ ^[0-9]{2}/[0-9]{2}/[0-9]{4}\ [0-9]{2}:[0-9]{2}:[0-9]{2}$ ]]; then
        log_error "Invalid Timestamp format: $INPUT_REQUESTED_TIMESTAMP."
        log_error "Expected input format: DD/MM/YYYY HH:MM:SS"
        exit 1
    fi

    IFS='/ :' read -r V_DAY V_MONTH V_YEAR V_HOUR V_MINUTE V_SECOND <<< "$INPUT_REQUESTED_TIMESTAMP"
    if (( 10#$V_MONTH < 1 || 10#$V_MONTH > 12 )); then log_error "Invalid Month: $V_MONTH"; exit 1; fi
    if (( 10#$V_DAY < 1 || 10#$V_DAY > 31 )); then log_error "Invalid Day: $V_DAY"; exit 1; fi
    if (( 10#$V_HOUR < 0 || 10#$V_HOUR > 23 )); then log_error "Invalid Hour: $V_HOUR"; exit 1; fi
    if (( 10#$V_MINUTE < 0 || 10#$V_MINUTE > 59 )); then log_error "Invalid Minute: $V_MINUTE"; exit 1; fi
    if (( 10#$V_SECOND < 0 || 10#$V_SECOND > 59 )); then log_error "Invalid Second: $V_SECOND"; exit 1; fi

    # Convert to standard ISO 8601 format
    REQUESTED_TIMESTAMP="${V_YEAR}-${V_MONTH}-${V_DAY}T${V_HOUR}:${V_MINUTE}:${V_SECOND}"
    echo "Successfully parsed requested timestamp. Using ISO 8601 format: $REQUESTED_TIMESTAMP"

    log_info "Input Validation Complete."
}

function prepare_variables() {
    echo "==========================================================================="
    echo "                          Preparing Variables                              "
    echo "==========================================================================="
    log_info "Preparing Variables..."

    # Normalize inputs
    TENANT_NAME=$(echo "$INPUT_TENANT_NAME" | tr '[:upper:]' '[:lower:]')
    raw_tenant_project=$(echo "$INPUT_TENANT_PROJECT" | tr '[:upper:]' '[:lower:]')

    if [[ "$raw_tenant_project" == dcsc-* ]]; then
        TENANT_PROJECT="$raw_tenant_project"
    else
        TENANT_PROJECT="dcsc-$raw_tenant_project"
    fi

    CURRENT_OFFSET=$(date +%z | sed 's/^\(...\)\(..\)$/\1:\2/')
    REQUESTED_TIMESTAMP="${REQUESTED_TIMESTAMP}${CURRENT_OFFSET}"
    DECOMMISSION_TIMESTAMP=$(date +'%Y-%m-%dT%H:%M:%S')
    DECOMMISSION_TIMESTAMP="${DECOMMISSION_TIMESTAMP}${CURRENT_OFFSET}"
    DATE_SUFFIX=$(date -d "$DECOMMISSION_TIMESTAMP" +'%Y_%m_%d_T_%H_%M')

    # Directories
    CLUSTER_DIR="${INPUT_TARGET_CLUSTER}"
    CUSTOMER_DIR="${CLUSTER_DIR}/${TENANT_NAME}"
    PROJECT_DIR="${CUSTOMER_DIR}/${TENANT_PROJECT}"
    PROJECT_DIR_CSO="${CUSTOMER_DIR}/dcsc-cso-${TENANT_NAME}"
    TENANT_METADATA_FILE="${CUSTOMER_DIR}/tenant-metadata.yaml"
    MESH_VALUES_FILE_PATH="${CUSTOMER_DIR}/dcsc-${TENANT_NAME}-service-mesh/values.yaml"
    IPPOOL_FILE="${INPUT_TARGET_CLUSTER}/egressip-pool.yaml"
    VALUES_FILE_CSO="${PROJECT_DIR_CSO}/values.yaml"

    # Decommission Paths
    DECOM_NS_DIR="${CUSTOMER_DIR}/.decommissioned_namespaces"
    DECOM_TENANTS_BASE="${CLUSTER_DIR}/.decommissioned_tenants"

    NEW_BRANCH_NAME="feat/decommission-${TENANT_PROJECT}"

    export TENANT_NAME TENANT_PROJECT REQUESTED_TIMESTAMP DECOMMISSION_TIMESTAMP DATE_SUFFIX

    log_info "Variables prepared."
    log_info "Timestamps set to Zone: CET ($CURRENT_OFFSET)"
    log_info "Target: $TENANT_PROJECT in $TENANT_NAME"
}

function sanity_checks() {
    echo "==========================================================================="
    echo "                             Sanity Checks                                 "
    echo "==========================================================================="
    log_info "Running Sanity Checks..."
    
    # Check remote branch
    if git ls-remote --exit-code --heads "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME" > /dev/null 2>&1; then
        log_error "Branch '$NEW_BRANCH_NAME' already exists."
        exit 1
    fi

    if [ ! -d "$CUSTOMER_DIR" ]; then
        log_error "Tenant directory '$CUSTOMER_DIR' does not exist."
        exit 1
    fi
    
    if [ ! -f "$TENANT_METADATA_FILE" ]; then
        log_error "Metadata file not found at '$TENANT_METADATA_FILE'."
        exit 1
    fi

    if [[ "${INPUT_DECOMMISSION_CSO,,}" == "true" ]]; then

      if [ ! -f "$VALUES_FILE_CSO" ]; then
          log_error "Critical: values.yaml not found at '$VALUES_FILE_CSO'."
          log_error "Cannot capture state before decommissioning. Aborting."
          exit 1
      fi

      # Check if namespace is active
      IS_ACTIVE=$(yq ".active_cso[] | select(.name == \"$TENANT_PROJECT\") | .name" "$TENANT_METADATA_FILE")
      if [ -z "$IS_ACTIVE" ]; then
          log_error "CSO '$TENANT_PROJECT' is not listed in active_cso."
          exit 1
      fi

    else

      if [ ! -f "$PROJECT_DIR/values.yaml" ]; then
          log_error "Critical: values.yaml not found at '$PROJECT_DIR/values.yaml'."
          log_error "Cannot capture state before decommissioning. Aborting."
          exit 1
      fi

      # Check if namespace is active
      IS_ACTIVE=$(yq ".active_namespaces[] | select(.name == \"$TENANT_PROJECT\") | .name" "$TENANT_METADATA_FILE")
      if [ -z "$IS_ACTIVE" ]; then
          log_error "Namespace '$TENANT_PROJECT' is not listed in active_namespaces."
          exit 1
      fi

    fi

}

function update_metadata() {
    echo "==========================================================================="
    echo "                Project Decommissioning - Metadata Update                  "
    echo "==========================================================================="
    log_info "Updating Tenant Metadata..."

    # 1. Extract the namespace object
    # 2. Add decommission fields
    # 3. Append to decommissioned_namespaces
    # 4. Remove from active_namespaces

    if [[ "${INPUT_DECOMMISSION_CSO,,}" == "true" ]]; then
      yq -i '
        (.active_cso[] | select(.name == strenv(TENANT_PROJECT))) as $item |
        
        $item.namespace_decommission_request_ticket = strenv(INPUT_REQUEST_ID) |
        $item.decommission_requested_timestamp = strenv(REQUESTED_TIMESTAMP) |
        $item.decommissioned_timestamp = strenv(DECOMMISSION_TIMESTAMP) |
  
        .decommissioned_cso += [$item] |
  
        del(.active_cso[] | select(.name == strenv(TENANT_PROJECT)))
      ' "$TENANT_METADATA_FILE"
    else
      yq -i '
        (.active_namespaces[] | select(.name == strenv(TENANT_PROJECT))) as $item |
        
        $item.namespace_decommission_request_ticket = strenv(INPUT_REQUEST_ID) |
        $item.decommission_requested_timestamp = strenv(REQUESTED_TIMESTAMP) |
        $item.decommissioned_timestamp = strenv(DECOMMISSION_TIMESTAMP) |
  
        .decommissioned_namespaces += [$item] |
  
        del(.active_namespaces[] | select(.name == strenv(TENANT_PROJECT)))
      ' "$TENANT_METADATA_FILE"

      # Move any active_registry_mirrors for this namespace to decommissioned_registry_mirrors
      log_info "Checking for active registry mirrors in namespace $TENANT_PROJECT..."
      yq -i '
        [.active_registry_mirrors[] | select(.namespace == strenv(TENANT_PROJECT)) | . + {
          "namespace_decommission_request_ticket": strenv(INPUT_REQUEST_ID),
          "decommission_requested_timestamp": strenv(REQUESTED_TIMESTAMP),
          "decommissioned_timestamp": strenv(DECOMMISSION_TIMESTAMP)
        }] as $items |
        .decommissioned_registry_mirrors += $items |
        del(.active_registry_mirrors[] | select(.namespace == strenv(TENANT_PROJECT)))
      ' "$TENANT_METADATA_FILE"
    fi

    log_info "Metadata updated."
}

function update_service_mesh() {
    if [ -f "$MESH_VALUES_FILE_PATH" ]; then
        log_info "Service Mesh configuration found. Removing namespace from mesh..."
        
        # Remove the namespace from the list
        yq -i 'del(.["dcs-service-mesh"].dataplane.namespaces[] | select(.name == strenv(TENANT_PROJECT)))' "$MESH_VALUES_FILE_PATH"
        
        # Smart Check: If list is empty, ensure it is explicit empty array []
        COUNT=$(yq '.["dcs-service-mesh"].dataplane.namespaces | length' "$MESH_VALUES_FILE_PATH")
        if [ "$COUNT" -eq 0 ]; then
             log_info "No namespaces left in mesh. Resetting to empty list."
             yq -i '.["dcs-service-mesh"].dataplane.namespaces = []' "$MESH_VALUES_FILE_PATH"
        fi
        
        log_info "Service Mesh configuration updated."
    else
        log_info "No Service Mesh configuration found for this tenant. Skipping mesh update."
    fi
}

function perform_decommission() {
    echo "==========================================================================="
    echo "               Project Decommissioning - Directory Update                  "
    echo "==========================================================================="
    log_info "Checking active namespaces count..."
    
    ACTIVE_NS_COUNT=$(yq '.active_namespaces | length' "$TENANT_METADATA_FILE")
    ACTIVE_TNT_COUNT=$(yq '.active_sub_tenants | length' "$TENANT_METADATA_FILE")
    ACTIVE_COUNT=$(($ACTIVE_NS_COUNT + $ACTIVE_TNT_COUNT))
    log_info "Remaining Active Namespaces: $ACTIVE_COUNT"

    if [ "$ACTIVE_COUNT" -gt 0 ]; then
        log_info "Tenant remains active. Moving values file to decommissioned folder..."
        
        mkdir -p "$DECOM_NS_DIR"

        mv "$PROJECT_DIR/values.yaml" "$DECOM_NS_DIR/${TENANT_PROJECT}_${DATE_SUFFIX}_values.yaml"
        
        log_info "Removing project directory: $PROJECT_DIR"
        rm -rf "$PROJECT_DIR"
        
    else
        log_info "No active namespaces left. Decommissioning Tenant..."

        TARGET_TENANT_DIR="${DECOM_TENANTS_BASE}/${TENANT_NAME}_${DATE_SUFFIX}"
        mkdir -p "$TARGET_TENANT_DIR"

        # Move Metadata
        mv "$TENANT_METADATA_FILE" "$TARGET_TENANT_DIR/"

        # Move Current Values File
        mv "$PROJECT_DIR/values.yaml" "$TARGET_TENANT_DIR/${TENANT_PROJECT}_${DATE_SUFFIX}_values.yaml"

        # Move previously decommissioned files (if any)
        if [ -d "$DECOM_NS_DIR" ]; then
            log_info "Moving historical decommissioned files..."
            # Check if directory is not empty
            if [ "$(ls -A $DECOM_NS_DIR)" ]; then
                mv "$DECOM_NS_DIR"/* "$TARGET_TENANT_DIR/"
            fi
        fi

        # Remove the Tenant Directory
        log_info "Removing tenant directory: $CUSTOMER_DIR"
        rm -rf "$CUSTOMER_DIR"
    fi
}


function perform_decommission_cso() {
    echo "==========================================================================="
    echo "               CSO Decommissioning                                    "
    echo "==========================================================================="

    # egressip tenant CSO(cluster scope object) decommission
    if [[ "${TENANT_PROJECT}" == dcsc-ei-* ]]; then
      echo "==========================================================================="
      echo "               EgressIP Decommissioning                                    "
      echo "==========================================================================="
      log_info "Releasing IP from the cluster pool"
  
      # Ensure the variable is exported for yq to read it
      export EGRESSIP_NAME="${TENANT_PROJECT}"
  
      log_info "Starting decommission for EgressIP object: $EGRESSIP_NAME"
  
      # Get the list of assigned IPs from the values file
      ASSIGNED_IPS=$(yq -r '.dcs-egress.egressIPResources[] | select(.name == strenv(EGRESSIP_NAME)) | .egressIPs[]' "$VALUES_FILE_CSO")
  
      # Check if the object had any IPs assigned to it
      if [ -n "$ASSIGNED_IPS" ]; then
  
        # Loop through the IPs and release them in the pool file
        for IP in $ASSIGNED_IPS; do
          export TARGET_IP="$IP"
  
          # We search all subnets (.[] | .ips[]) for the specific IP to reset its status and clear the object
          yq -i '(.[] | .ips[] | select(.ip == strenv(TARGET_IP))) |= (.status = "available" | .object = "")' "$IPPOOL_FILE"
  
          log_info "Successfully released IP: $TARGET_IP back to the available pool."
        done
  
      else
  
        log_info "No IPs found for $EGRESSIP_NAME (or the object didn't exist)."
  
      fi
  
      # Delete the entire entry for this tenant from the egressIPResources array
      yq -i 'del(.dcs-egress.egressIPResources[] | select(.name == strenv(EGRESSIP_NAME)))' "$VALUES_FILE_CSO"
  
      log_info "Successfully removed $EGRESSIP_NAME from $VALUES_FILE_CSO"
    fi

    log_info "Checking active CSO(cluster scope object) count..."
    ACTIVE_COUNT=$(yq '.active_cso | length' "$TENANT_METADATA_FILE")
    log_info "Current Active CSO objects: $ACTIVE_COUNT"

    if [ ! "$ACTIVE_COUNT" -gt 0 ]; then
      log_info "No active tenant CSO(cluster scope object)  left. Decommissioning CSO Project $PROJECT_DIR_CSO"
      rm -rf "$PROJECT_DIR_CSO"
    fi

}

function run_git_ops() {
    log_info "Committing changes..."
    git config --global user.email "${GITLAB_USER_EMAIL}"
    git config --global user.name "${GITLAB_USER_NAME}"
    git checkout -b "$NEW_BRANCH_NAME"
    git add "$CLUSTER_DIR"
    git add "$IPPOOL_FILE"
    git commit -m "chore: Decommission $TENANT_PROJECT in $TENANT_NAME"
    git push "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME"
    echo ""
    log_info "Decommissioning Complete. Branch '$NEW_BRANCH_NAME' pushed."
    echo ""
    echo "---------------------------------------------------------------------------"
    echo "| **  Please create a Merge Request from this branch to continue.   **    |"
    echo "---------------------------------------------------------------------------"
}

# --- Main Execution ---
if [[ "${DEBUG}" == "true" ]]; then
    echo "==========================================================================="
    echo "                         *** Debug Enabled ***                             "
    echo "==========================================================================="
    set -x
fi

validate_inputs
prepare_variables
sanity_checks
update_metadata

if [[ "${INPUT_DECOMMISSION_CSO,,}" == "true" ]]; then
  perform_decommission_cso
else
 update_service_mesh
 perform_decommission
fi

run_git_ops
