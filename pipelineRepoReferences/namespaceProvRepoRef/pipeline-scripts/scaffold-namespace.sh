#!/bin/bash
# =============================================================================
# scaffold-namespace.sh  (was scaffold.sh)
#
# Creates or updates a namespace, or creates a tenant EgressIP cluster-scope
# object. Which one is decided by OPERATION, via INPUT_CREATE_CSO.
#
# WHERE VALIDATION LIVES NOW
# --------------------------
# This script used to open with a 126-line validate_inputs that normalised case,
# compared every field against the placeholder string declared in
# .gitlab-ci.yml, and parsed DD/MM/YYYY timestamps. All of that has moved to
# request-schema.yaml, enforced by load-payload.sh before the first line below
# runs.
#
# The split is: the schema owns syntax — presence, type, enum, format,
# normalisation, and cross-field rules like "ARD is required for prod". This
# script owns what the schema cannot know, which is everything that needs the
# repository on disk: does the tenant directory exist, is the ArgoCD app name
# already taken, does the mesh this namespace wants to join actually exist.
# Those live in sanity_checks and are untouched.
#
# Keeping a second copy of the syntax rules here as belt-and-braces was the
# original design, and it is what produced a siglum check that could never fire
# — the sentinel was written in a different case from the value it was compared
# against. One declaration, one place to look.
# =============================================================================
set -e

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_HERE}/common.sh"
source "${_HERE}/load-payload.sh"

function prepare_variables() {
    echo "==========================================================================="
    echo "                          Preparing Variables                              "
    echo "==========================================================================="
    log_info "Preparing Variables..."


    # Default var values
    SUFFIX_MAX_CHARS=4
    # We are limited by the helm to have a maximum 52 chars for argocd app name 
    NS_MAX_CHARS=50
    # Number of fix characters dcsc--2f9w
    NS_FIX_CHARS=10
    # Number of characters dcsc-ds--9g4q  
    DS_FIX_CHARS=13

    # Generate chars for random suffix string
    RANDOM_SUFFIX=$({ shuf -n 2 -re {a..z}; shuf -n 2 -re {0..9}; } | shuf | tr -d '\n' | head -c $SUFFIX_MAX_CHARS)
    RANDOM_SUFFIX10=$({ shuf -n 5 -re {a..z}; shuf -n 5 -re {0..9}; } | shuf | tr -d '\n' | head -c 10)

    # Kubernetes label value doesn't allow '\'. Normalize the value.
    COST_CENTER_LABEL_VALUE="${INPUT_COST_CENTER//\//-}"

    # Tenant name Suffix Logic
    TENANT_DIR="${INPUT_TARGET_CLUSTER}/${INPUT_TENANT_NAME}"
    if [[ -d "$TENANT_DIR" ]]; then
        log_info "Tenant  $TENANT_DIR exists."
        TENANT_NAME=$INPUT_TENANT_NAME
    else
        TENANT_NAME="${INPUT_TENANT_NAME}-${RANDOM_SUFFIX}"
        log_info "We will generate a new tenant $TENANT_NAME"
    fi
    
    CUSTOMER_DIR="${INPUT_TARGET_CLUSTER}/${TENANT_NAME}"

    # Check if user provided an EXACT existing project to UPDATE
    if [ -n "$INPUT_NAMESPACE_NAME" ] && [ "$INPUT_NAMESPACE_NAME" != "dcsc-" ] && [ -d "${CUSTOMER_DIR}/${INPUT_NAMESPACE_NAME}" ]; then
        TENANT_PROJECT="${INPUT_NAMESPACE_NAME}"
        log_info "Existing project provided for update: $TENANT_PROJECT"
    elif [[ "${INPUT_CREATE_CSO,,}" == "true" ]]; then
        # CSO overrides project naming completely, bypassing empty namespace checks
        TENANT_PROJECT_FULL="dcsc-cso-${INPUT_TENANT_NAME}"
        TENANT_PROJECT=$(echo "$TENANT_PROJECT_FULL" | head -c $((NS_MAX_CHARS - 12)))
        log_info "CSO creation selected. Project name set to: $TENANT_PROJECT"
    elif [[ "${INPUT_CREATE_SERVICE_MESH,,}" == "true" ]]; then
        # BUG FIX. Deploying a mesh was unreachable: sanity_checks requires
        # TENANT_PROJECT to equal "dcsc-${TENANT_NAME}-service-mesh", but with no
        # branch here the name fell through to the generic rule below and picked
        # up the random suffix -- "dcsc-tenanta-service-mesh-a1b2" -- so the
        # equality could never hold, on any input. The operator could not even
        # pre-type the suffix, because it is regenerated on every run.
        #
        # CSO and DevSpace both override the name here without a suffix; mesh was
        # the one that did not. This is the missing branch.
        TENANT_PROJECT="dcsc-${TENANT_NAME}-service-mesh"
        log_info "Service mesh deployment selected. Project name set to: $TENANT_PROJECT"
    elif [[ "${INPUT_IS_DEVSPACE,,}" == "true" ]]; then
        # DevSpace overrides project naming completely, bypassing empty namespace checks
        # 1. Extract everything before the '@' symbol
        EMAIL_PREFIX="${INPUT_REQUESTER_EMAIL%%@*}"
        # 2. Extract first and last name (ignoring middle names/words)
        FORMATTED_USER=$(echo "$EMAIL_PREFIX" | awk -F'[._-]+' '{if (NF>1) print $1 "-" $NF; else print $1}' | head -c $((NS_MAX_CHARS - DS_FIX_CHARS)))
        # 3. Set TENANT_PROJECT
        log_info "DevSpace creation selected. Adding 'dcsc-ds' prefix and random suffix."
        TENANT_PROJECT="dcsc-ds-${FORMATTED_USER}-${RANDOM_SUFFIX}"
    else
        # Tenant Project Prefix and Suffix Logic
        if [[ "$INPUT_NAMESPACE_NAME" == "dcsc-" ]] || [[ -z "$INPUT_NAMESPACE_NAME" ]]; then
            # Prevent duplicate ambiguous namespaces if tenant already exists
            if [[ -d "$TENANT_DIR" ]]; then
                echo "==========================================================================="
                log_error "Tenant '$INPUT_TENANT_NAME' already exists."
                log_error "You cannot leave the Project Name empty/default for an existing tenant."
                log_error "Please explicitly provide the existing namespace name (e.g., dcsc-...) to update it, or provide a new name to create an additional one."
                echo "==========================================================================="
                exit 1
            fi
            log_info "Project name left as default. Defaulting to Tenant Name."
            TENANT_PROJECT_INPUT="${INPUT_TENANT_NAME}"
        elif [[ "$INPUT_NAMESPACE_NAME" == dcsc-* ]]; then
            TENANT_PROJECT_INPUT="${INPUT_NAMESPACE_NAME#dcsc-}"
        else
            TENANT_PROJECT_INPUT="$INPUT_NAMESPACE_NAME"
        fi

        MAX_PROJECT_CHARS=$((NS_MAX_CHARS - NS_FIX_CHARS))

        if [[ ${#TENANT_PROJECT_INPUT} -gt $MAX_PROJECT_CHARS ]]; then
            log_info "Warning: Tenant project exceeds $NS_MAX_CHARS characters. Truncating."
            TENANT_PROJECT_INPUT=$(echo "$TENANT_PROJECT_INPUT" | cut -c 1-"$MAX_PROJECT_CHARS")
            log_info "Warning: New namespace name dcsc-${TENANT_PROJECT_INPUT}-${RANDOM_SUFFIX}"
        fi

        TENANT_PROJECT="dcsc-${TENANT_PROJECT_INPUT}-${RANDOM_SUFFIX}"
    fi

    # Calculate expiration dates if route exception is enabled
    if [[ "$INPUT_ROUTE_EXCEPTION" == "true" ]]; then
        EXCEPTION_GRANTED_DATE=$(date +'%Y-%m-%d')
        # Adds exactly 90 days to the granted date
        EXCEPTION_EXPIRES_DATE=$(date -d "+90 days" +'%Y-%m-%d')
        export EXCEPTION_GRANTED_DATE EXCEPTION_EXPIRES_DATE
    fi

    # Set Vars
    CURRENT_OFFSET=$(date +%z | sed 's/^\(...\)\(..\)$/\1:\2/')
    # Already ISO 8601: the operator pastes DD/MM/YYYY HH:MM:SS from MyITSM and
    # load-payload.sh reassembles it, so the conversion validate_inputs used to
    # do here now happens once for every operation instead of once per script.
    REQUESTED_TIMESTAMP="${INPUT_REQUESTED_TIMESTAMP}${CURRENT_OFFSET}"
    PROVISION_TIMESTAMP=$(date +'%Y-%m-%dT%H:%M:%S')
    PROVISION_TIMESTAMP="${PROVISION_TIMESTAMP}${CURRENT_OFFSET}"

    PROJECT_DIR="${CUSTOMER_DIR}/${TENANT_PROJECT}"
    VALUES_FILE="${PROJECT_DIR}/values.yaml"
    CHART_FILE="${PROJECT_DIR}/Chart.yaml"
    HELMIGNORE_FILE="${PROJECT_DIR}/.helmignore"
    MESH_VALUES_FILE_PATH="${CUSTOMER_DIR}/dcsc-${TENANT_NAME}-service-mesh/values.yaml"
    TENANT_METADATA_FILE="${CUSTOMER_DIR}/tenant-metadata.yaml"
    TEMPLATE_DIR="./customers-templates"
    IPPOOL_FILE="${INPUT_TARGET_CLUSTER}/egressip-pool.yaml"
    EGRESSIP_NAME="dcsc-ei-${RANDOM_SUFFIX10}"
    
    IS_EXISTING_PROJECT="false"
    if [ -d "$PROJECT_DIR" ]; then
        IS_EXISTING_PROJECT="true"
        NEW_BRANCH_NAME="feat/update-${TENANT_PROJECT}-$(date +%s)"
        log_info "Existing project detected. Operating in UPDATE mode."
    else
        NEW_BRANCH_NAME="feat/onboard-${TENANT_PROJECT}"
        log_info "New project detected. Operating in CREATION mode."
    fi

    # Export calculated variables
    export TENANT_NAME TENANT_PROJECT PROVISION_TIMESTAMP REQUESTED_TIMESTAMP CUSTOMER_DIR RANDOM_SUFFIX EGRESSIP_NAME COST_CENTER_LABEL_VALUE IS_EXISTING_PROJECT

    log_info "Variables prepared."
    log_info "Timestamps set to Zone: CET ($CURRENT_OFFSET)"
}

function sanity_checks() {
    echo "==========================================================================="
    echo "                             Sanity Checks                                 "
    echo "==========================================================================="
    log_info "Running Sanity Checks..."

    # Does the request match what is actually on disk?
    #
    # INPUT_MODE says what the operator asked for; IS_EXISTING_PROJECT says what
    # is there. Before the operations were split, this script inferred the
    # intent, so asking to update a namespace that did not exist quietly created
    # it, and a create against an existing name quietly modified it. Neither is
    # something anyone wants to discover in a merge request.
    #
    # Not set for cso.create, which legitimately runs against an existing CSO
    # directory when adding a second EgressIP to a tenant.
    if [ -n "${INPUT_MODE:-}" ]; then
        if [ "$INPUT_MODE" = "update" ] && [ "$IS_EXISTING_PROJECT" != "true" ]; then
            echo "==========================================================================="
            log_error "Update requested, but '$PROJECT_DIR' does not exist."
            log_error "Check the namespace name, or use the create operation instead."
            echo "==========================================================================="
            exit 1
        fi
        if [ "$INPUT_MODE" = "create" ] && [ "$IS_EXISTING_PROJECT" = "true" ]; then
            echo "==========================================================================="
            log_error "Create requested, but '$PROJECT_DIR' already exists."
            log_error "Use the update operation to change it."
            echo "==========================================================================="
            exit 1
        fi
    fi

    # Check Branch
    if git ls-remote --exit-code --heads "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME" > /dev/null 2>&1; then
        log_error "Branch '$NEW_BRANCH_NAME' already exists."
        exit 1
    fi

    # Check Local Dir (Allows updates if IS_EXISTING_PROJECT is true and values.yaml exists)
    if [ "$IS_EXISTING_PROJECT" == "true" ] && [[ "$PROJECT_DIR" != *"dcsc-cso-${TENANT_NAME}" ]] && [ ! -f "$PROJECT_DIR/values.yaml" ]; then
        log_error "Project path already exists but values.yaml is missing: $PROJECT_DIR"
        exit 1
    fi

    # Check Mesh Conflicts
    if [ "$INPUT_CREATE_SERVICE_MESH" = "true" ] && [ "$IS_EXISTING_PROJECT" == "false" ]; then
        if [ -f "$MESH_VALUES_FILE_PATH" ]; then
            log_error "Service mesh already exists at '$MESH_VALUES_FILE_PATH'."
            exit 1
        fi
        if [[ "$TENANT_PROJECT" != "dcsc-${TENANT_NAME}-service-mesh" ]]; then
            log_error "Project Name Mismatch. Expected 'dcsc-${TENANT_NAME}-service-mesh'."
            exit 1
        fi
    fi

    # Check if the argocd app name will be unique (ignoring dcsc-cso paths AND skipping if updating)
    if [ "$IS_EXISTING_PROJECT" == "false" ]; then
        MATCHING_PROJECT_DIR=$(find . -mindepth 3 -maxdepth 3 -type d -name "$TENANT_PROJECT" ! -path "*dcsc-cso-${TENANT_NAME}" -print -quit)
        if [[ -n "$MATCHING_PROJECT_DIR" ]]; then
          log_error "The project '$TENANT_PROJECT' already exists at path: '$MATCHING_PROJECT_DIR'"
          log_error "We need a unique project name that will be used for the ArgoCD app name and registry project name."
          exit 1
        fi
    fi

    # Check if the user already has a devspace namespace
    if [[ "${INPUT_IS_DEVSPACE,,}" == "true" ]] && [ "$IS_EXISTING_PROJECT" == "false" ]; then
      RESULT=$(find "$INPUT_TARGET_CLUSTER" -name "values.yaml" -type f -exec yq e 'select((."dcs-namespace-provisioner".devspaceConfig.isDevspace == true or ."dcs-namespace-provisioner".devspaceConfig.isDevspace == "true") and ."dcs-namespace-provisioner".devspaceConfig.devspaceUser == "'"${INPUT_REQUESTER_EMAIL}"'") | ."dcs-namespace-provisioner".project_namespace + "|" + ."dcs-namespace-provisioner".requiredLabels."dcs.zzz.com/tenant_name"' {} + 2>/dev/null | grep -v -e '^null|null$' -e '^|$' -e '^$' || true)

      if [[ -n "$RESULT" ]]; then
        # Split the RESULT string based on the pipe "|" delimiter
        EXISTING_NAMESPACE="${RESULT%|*}"
        EXISTING_TENANT="${RESULT#*|}"

        log_error "User $INPUT_REQUESTER_EMAIL already has an active devspace namespace: $EXISTING_NAMESPACE Tenant name: $EXISTING_TENANT"
        exit 1
      fi
    fi

    if [ "$INPUT_JOIN_SERVICE_MESH" = "true" ]; then
        if [ "$INPUT_CREATE_SERVICE_MESH" = "true" ]; then
            log_error "Cannot Deploy Mesh AND add namespace to it simultaneously."
            exit 1
        fi
        if [ ! -f "$MESH_VALUES_FILE_PATH" ]; then
            log_error "Service mesh not found at $MESH_VALUES_FILE_PATH"
            exit 1
        fi
    fi
}

function update_metadata() {
    echo "==========================================================================="
    echo "                    Scaffolding - Metadata Update                          "
    echo "==========================================================================="
    log_info "Updating Metadata..."

    if [ ! -d "$CUSTOMER_DIR" ]; then
        log_info "Tenant directory does not exist. Creating: $CUSTOMER_DIR"
        mkdir -p "$CUSTOMER_DIR"
    fi

    # CREATE BASE FILE (If brand new tenant)
    if [ ! -f "$TENANT_METADATA_FILE" ]; then
      log_info "Creating base tenant metadata file..."
      yq -n '
        .tenant_name = strenv(TENANT_NAME) |
        .requester = strenv(INPUT_REQUESTER_EMAIL) |
        .tenant_request_ticket = strenv(INPUT_REQUEST_ID) |
        .siglum = strenv(INPUT_SIGLUM) |
        .cost_center = strenv(INPUT_COST_CENTER) |
        .requested_timestamp = strenv(REQUESTED_TIMESTAMP) |
        .provision_timestamp = strenv(PROVISION_TIMESTAMP) |
        .gpu_enabled = strenv(INPUT_GPU_ENABLED) |
        with(select(strenv(INPUT_GPU_ENABLED) == "true"); .gpu_tier = strenv(INPUT_GPU_TIER)) |
        .active_namespaces = [] |
        .active_cso = []
      ' > "$TENANT_METADATA_FILE"
    fi

    # HANDLE CSO LOGIC
    if [[ "${INPUT_CREATE_CSO,,}" == "true" ]]; then
      CSO_EXISTS=$(yq e ".active_cso[] | select(.name == \"$EGRESSIP_NAME\") | .name" "$TENANT_METADATA_FILE" 2>/dev/null)
      
      if [ -z "$CSO_EXISTS" ]; then
          # NEW CSO: Append to array
          log_info "Appending new CSO to metadata..."
          yq e -i '
            .active_cso += [{
              "name": strenv(EGRESSIP_NAME),
              "requester": strenv(INPUT_REQUESTER_EMAIL),
              "namespace_request_ticket": strenv(INPUT_REQUEST_ID),
              "requested_timestamp": strenv(REQUESTED_TIMESTAMP),
              "provision_timestamp": strenv(PROVISION_TIMESTAMP)
            }]
          ' "$TENANT_METADATA_FILE"
      else
          # EXISTING CSO: Update Audit Trail
          log_info "CSO $EGRESSIP_NAME already in metadata. Appending to update history..."
          yq e -i '
            (.active_cso[] | select(.name == strenv(EGRESSIP_NAME))).update_history += [{
              "update_ticket": strenv(INPUT_REQUEST_ID),
              "updated_timestamp": strenv(PROVISION_TIMESTAMP)
            }]
          ' "$TENANT_METADATA_FILE"
      fi

    # HANDLE NAMESPACE LOGIC
    else
        NS_EXISTS=$(yq e ".active_namespaces[] | select(.name == \"$TENANT_PROJECT\") | .name" "$TENANT_METADATA_FILE" 2>/dev/null)
        
        if [ -z "$NS_EXISTS" ]; then
            # NEW NAMESPACE: Append to array
            log_info "Appending new Namespace to metadata..."
            if [[ "$INPUT_LIFECYCLE" == "prod" ]]; then
                yq e -i '
                    .active_namespaces += [{
                    "name": strenv(TENANT_PROJECT),
                    "requester": strenv(INPUT_REQUESTER_EMAIL),
                    "namespace_request_ticket": strenv(INPUT_REQUEST_ID),
                    "requested_timestamp": strenv(REQUESTED_TIMESTAMP),
                    "provision_timestamp": strenv(PROVISION_TIMESTAMP),
                    "lifecycle": strenv(INPUT_LIFECYCLE),
                    "ard": strenv(INPUT_ARD_LINK)
                    }]
                ' "$TENANT_METADATA_FILE"
            else
                yq e -i '
                    .active_namespaces += [{
                    "name": strenv(TENANT_PROJECT),
                    "requester": strenv(INPUT_REQUESTER_EMAIL),
                    "namespace_request_ticket": strenv(INPUT_REQUEST_ID),
                    "requested_timestamp": strenv(REQUESTED_TIMESTAMP),
                    "provision_timestamp": strenv(PROVISION_TIMESTAMP),
                    "lifecycle": strenv(INPUT_LIFECYCLE)
                    }]
                ' "$TENANT_METADATA_FILE"
            fi
        else
            # EXISTING NAMESPACE: Update Audit Trail
            log_info "Namespace $TENANT_PROJECT already in metadata. Appending to update history..."
            yq e -i '
              (.active_namespaces[] | select(.name == strenv(TENANT_PROJECT))).update_history += [{
                "update_ticket": strenv(INPUT_REQUEST_ID),
                "updated_timestamp": strenv(PROVISION_TIMESTAMP)
              }]
            ' "$TENANT_METADATA_FILE"
        fi
    fi

    # HANDLE ROUTE SECURITY EXCEPTION
    if [[ "$INPUT_ROUTE_EXCEPTION" == "true" ]]; then
        log_info "Adding Route security exception to metadata..."
        yq e -i '
          (.active_namespaces[] | select(.name == strenv(TENANT_PROJECT))).security_exception = {
            "request_ticket": strenv(INPUT_REQUEST_ID),
            "granted_at": strenv(EXCEPTION_GRANTED_DATE),
            "expires_at": strenv(EXCEPTION_EXPIRES_DATE)
          }
        ' "$TENANT_METADATA_FILE"
    fi

    log_info "Metadata updated."
}

function run_scaffold_project() {
    echo "==========================================================================="
    echo "                  Project Scaffolding - Directory Update                   "
    echo "==========================================================================="
    log_info "Creating directories..."
    mkdir -p "$PROJECT_DIR/docs"
    mkdir -p "$PROJECT_DIR/templates"

    if [ "$IS_EXISTING_PROJECT" == "false" ]; then
        log_info "Generating Project Files from templates..."
        cp "${TEMPLATE_DIR}/values.yaml.tpl" "$VALUES_FILE"
        
        if [ "$INPUT_CREATE_SERVICE_MESH" = "true" ]; then
            yq eval -i ". *= load(\"${TEMPLATE_DIR}/values-service-mesh.yaml.tpl\")" "$VALUES_FILE"
        fi

        if [ "$INPUT_IS_DEVSPACE" = "true" ]; then
            yq eval -i ". *= load(\"${TEMPLATE_DIR}/values-devspace.yaml.tpl\")" "$VALUES_FILE"
        fi

        # Replacements (Only needed on first creation) 
        sed -i "s|__TENANT_NAME__|${TENANT_NAME}|g" "$VALUES_FILE"
        sed -i "s|__TENANT_PROJECT__|${TENANT_PROJECT}|g" "$VALUES_FILE"
        sed -i "s|__TARGET_CLUSTER__|${INPUT_TARGET_CLUSTER}|g" "$VALUES_FILE"
        sed -i "s|__LIFECYCLE__|${INPUT_LIFECYCLE}|g" "$VALUES_FILE"
        sed -i "s|__SIGLUM__|${INPUT_SIGLUM}|g" "$VALUES_FILE"
        sed -i "s|__COST_CENTER__|${COST_CENTER_LABEL_VALUE}|g" "$VALUES_FILE"
        sed -i "s|__CONTACT_PERSON__|${INPUT_REQUESTER_EMAIL}|g" "$VALUES_FILE"
        sed -i "s|__NAMESPACE_IS_FOR_DEVSPACE__|${INPUT_IS_DEVSPACE}|g" "$VALUES_FILE"
        sed -i "s|__REQUESTER_EMAIL__|${INPUT_REQUESTER_EMAIL}|g" "$VALUES_FILE"
        sed -i "s|__APP_LABEL__|${TENANT_PROJECT#dcsc-}|g" "$VALUES_FILE"

        cp "${TEMPLATE_DIR}/Chart.yaml.tpl" "$CHART_FILE"
        if [ "$INPUT_CREATE_SERVICE_MESH" != "true" ]; then
            # Was: sed -i '/\s*-\s*name:\s*dcs-service-mesh/,+2d'
            #
            # That deleted the matching line plus exactly two more, so it was
            # correct only while the mesh dependency stayed exactly three lines
            # long. Add a fourth (a `condition:`, say) and sed leaves it behind
            # -- attached to the dependency above it. The result is still valid
            # YAML, which is the dangerous part: Helm would silently apply a
            # mesh condition to dcs-namespace-provisioner instead of failing.
            #
            # Structural deletion cannot land on the wrong dependency.
            yq e -i 'del(.dependencies[] | select(.name == "dcs-service-mesh"))' "$CHART_FILE"
        fi

        sed -i "s|__HARBOR_URL__|${HARBOR_LOCAL_URL}|g" "$CHART_FILE"
        sed -i "s|__HARBOR_OCI_PROJECT__|${HARBOR_OCI_PROJECT}|g" "$CHART_FILE"

        cp "${TEMPLATE_DIR}/helmignore.tpl" "$HELMIGNORE_FILE"
    else
        log_info "Existing project detected. Skipping template generation to preserve custom values."
    fi

    # =========================================================================
    # DYNAMIC UPDATES (Applies to BOTH New and Existing Projects)
    # =========================================================================

    log_info "Analysing Operator Services configurations..."
    if [[ "$INPUT_ARGOCD_OPERATOR" == "true" ]]; then
        log_info "Enabling ArgoCD Operator..."
        yq e -i '.dcs-namespace-provisioner.managedServices.argocdOperator.enabled = true' "$VALUES_FILE"
    fi
    if [[ "$INPUT_GITLAB_OPERATOR" == "true" ]]; then
        log_info "Enabling GitLab Operator..."
        yq e -i '.dcs-namespace-provisioner.managedServices.gitlabOperator.enabled = true' "$VALUES_FILE"
    fi
    if [[ "$INPUT_CLOUDNATIVEPG_OPERATOR" == "true" ]]; then
        log_info "Enabling CloudNativePG Operator..."
        yq e -i '.dcs-namespace-provisioner.managedServices.cloudNativePG.enabled = true' "$VALUES_FILE"
    fi
    if [[ "$INPUT_CERT_MANAGER_OPERATOR" == "true" ]]; then
        log_info "Enabling Cert Manager Operator..."
        yq e -i '.dcs-namespace-provisioner.managedServices.certManagerOperator.enabled = true' "$VALUES_FILE"
    fi
    if [[ "$INPUT_LOKI_OPERATOR" == "true" ]]; then
        log_info "Enabling Loki Operator..."
        yq e -i '.dcs-namespace-provisioner.managedServices.lokiOperator.enabled = true' "$VALUES_FILE"
    fi

    # --- GPU Configuration Logic ---
    if [[ "$INPUT_GPU_ENABLED" == "true" && "$INPUT_GPU_TIER" != "NONE" ]]; then
        log_info "Configuring GPU resources for tier: $INPUT_GPU_TIER"
        export GPU_TPL_PATH="${TEMPLATE_DIR}/values-gpuconfig.yaml.tpl"
        yq eval -i '. *= load(strenv(GPU_TPL_PATH)).[strenv(INPUT_GPU_TIER)]' "$VALUES_FILE"
    fi

    # Inject route exception settings into values.yaml
    if [[ "$INPUT_ROUTE_EXCEPTION" == "true" ]]; then
        log_info "Updating route Exception configurations in values.yaml..."
        yq e -i '
          .["dcs-namespace-provisioner"].routeException.enabled = true |
          .["dcs-namespace-provisioner"].routeException.requestId = strenv(INPUT_REQUEST_ID) |
          .["dcs-namespace-provisioner"].routeException.grantedAt = strenv(EXCEPTION_GRANTED_DATE)
        ' "$VALUES_FILE"
    fi

    if [ "$INPUT_JOIN_SERVICE_MESH" = "true" ]; then
        log_info "Updating Service Mesh Config safely..."
        yq e -i '
            .["dcs-service-mesh"].dataplane.namespaces += [{"name": strenv(TENANT_PROJECT)}] | 
            .["dcs-service-mesh"].dataplane.namespaces |= unique_by(.name)
        ' "$MESH_VALUES_FILE_PATH"
    fi

    if [ "$INPUT_IS_DEVSPACE" = "true" ]; then
        TENANT_DEFAULT_NS_VALUES_FILE_PATH="${CUSTOMER_DIR}/dcsc-${TENANT_NAME}/values.yaml"
        if [ -f "$TENANT_DEFAULT_NS_VALUES_FILE_PATH" ]; then
          log_info "Updating Tenant Default namespace project_users"
          yq e -i '."dcs-namespace-provisioner".project_user_config.project_users.initialUsers = (."dcs-namespace-provisioner".project_user_config.project_users.initialUsers + [strenv(INPUT_REQUESTER_EMAIL)] | unique)' "$TENANT_DEFAULT_NS_VALUES_FILE_PATH"
          yq e -i '."dcs-namespace-provisioner".project_user_config.project_users.initialUsers -= ."dcs-namespace-provisioner".project_owner_config.project_owner.initialUsers' "$TENANT_DEFAULT_NS_VALUES_FILE_PATH"
          USERS_LIST=$(yq e '."dcs-namespace-provisioner".project_user_config.project_users.initialUsers[]' "$TENANT_DEFAULT_NS_VALUES_FILE_PATH" 2>/dev/null)
          if [ -n "$USERS_LIST" ]; then
            yq e -i '."dcs-namespace-provisioner".project_user_config.user_rbac_enable = true' "$TENANT_DEFAULT_NS_VALUES_FILE_PATH"
          fi
        fi
    fi

    echo "---------------------------------------------------------------------------"
    echo "                             Project Details                               "
    echo "---------------------------------------------------------------------------"
    echo "Customer/Tenant:                        $TENANT_NAME"
    echo "Project/Namespace:                      $TENANT_PROJECT"
    echo "Cluster:                                $INPUT_TARGET_CLUSTER"
    echo "Lifecycle:                              $INPUT_LIFECYCLE"
    echo "This namespace is for devspace:         $INPUT_IS_DEVSPACE"
    echo "Add namespace to tenant service mesh:   $INPUT_JOIN_SERVICE_MESH"
    echo "Deploy tenant service mesh:             $INPUT_CREATE_SERVICE_MESH"
    echo "Route Exception:                        $INPUT_ROUTE_EXCEPTION"
    echo "Siglum:                                 $INPUT_SIGLUM"
    echo "Cost Center:                            $INPUT_COST_CENTER"
    echo "Req Time:                               $REQUESTED_TIMESTAMP"
    echo "Prov Time:                              $PROVISION_TIMESTAMP"
    echo "GPU Enabled:                            $INPUT_GPU_ENABLED"
    echo "---------------------------------------------------------------------------"
    echo "                             Project Paths                                 "
    echo "---------------------------------------------------------------------------"
    echo "Project Directory:                      $PROJECT_DIR"
    echo "Project Values File:                    $VALUES_FILE"
    echo "Project Chart File:                     $CHART_FILE"
    echo "Project Helmignore File:                $HELMIGNORE_FILE"
    echo "Tenant Metadata File:                   $TENANT_METADATA_FILE"
    echo "---------------------------------------------------------------------------"
}

function validate_security_policies() {
    echo "==========================================================================="
    echo "                         Security Policy Check                             "
    echo "==========================================================================="
    
    local TARGET_FILE="${VALUES_FILE}"
    
    log_info "Checking security compliance for $INPUT_LIFECYCLE..."
    log_info "Target file: $TARGET_FILE"
    if [[ "$INPUT_LIFECYCLE" == "prod" ]]; then
        if [[ ! -f "$TARGET_FILE" ]]; then
            log_error "CRITICAL: $TARGET_FILE does not exist. Cannot validate security."
            exit 1
        fi
        
        echo "------------------------------------------------------------"
        set +e
        INVALID_PUSH_FOUND=$(yq -e '."dcs-namespace-provisioner".harborRobotAccounts.robotAccounts[] | select(.default == false) | .permissions[] | select(.action == "push")' "$TARGET_FILE" 2>/dev/null)
        set -e

        if [[ -n "$INVALID_PUSH_FOUND" ]]; then
            echo "============================================================"
            echo "🚨 SECURITY VIOLATION: FORBIDDEN PUSH PERMISSIONS IN PROD 🚨"
            echo "============================================================"
            echo "File: $TARGET_FILE"
            echo ""

            grep -n -B 1 -E "action: [\"']?push[\"']?" "$TARGET_FILE" | grep -v "^--"     
            
            echo ""
            echo "============================================================"
            log_error "Custom Robot Accounts in PROD are NOT allowed to have 'push' permissions."
            log_error "Please remove these actions from your $VALUES_FILE."
            exit 1
        fi
        log_info "Security check passed: No unauthorized push permissions found for PROD."
    else
        log_info "Skipping push-restriction check (Lifecycle is $INPUT_LIFECYCLE)."
    fi
}

function run_scaffold_cso() {
    echo "==========================================================================="
    echo "                  Egress Scaffolding - Directory Update                   "
    echo "==========================================================================="

    log_info "Generating or updating Project Files..."
    # Check and create values file
    if [ ! -f "$VALUES_FILE" ]; then
        mkdir -p "$PROJECT_DIR"
        log_info "CSO values file does not exist. Creating: $VALUES_FILE"
        cp "${TEMPLATE_DIR}/values-CSO.yaml.tpl" "$VALUES_FILE"
        # Replacements
        sed -i "s|__TENANT_NAME__|${TENANT_NAME}|g" "$VALUES_FILE"
        sed -i "s|__TARGET_CLUSTER__|${INPUT_TARGET_CLUSTER}|g" "$VALUES_FILE"
        sed -i "s|__LIFECYCLE__|${INPUT_LIFECYCLE}|g" "$VALUES_FILE"
        sed -i "s|__COST_CENTER__|${COST_CENTER_LABEL_VALUE}|g" "$VALUES_FILE"
        sed -i "s|__CONTACT_PERSON__|${INPUT_REQUESTER_EMAIL}|g" "$VALUES_FILE"
        sed -i "s|__RANDOM_SUFFIX__|${RANDOM_SUFFIX}|g" "$VALUES_FILE"
    fi

    # Check and create chart file
    if [ ! -f "$CHART_FILE" ]; then
      log_info "CSO chart file does not exist. Creating: $CHART_FILE"
      cp "${TEMPLATE_DIR}/Chart-CSO.yaml.tpl" "$CHART_FILE"
      cp "${TEMPLATE_DIR}/helmignore.tpl" "$HELMIGNORE_FILE"

      sed -i "s|__HARBOR_URL__|${HARBOR_LOCAL_URL}|g" "$CHART_FILE"
      sed -i "s|__HARBOR_OCI_PROJECT__|${HARBOR_OCI_PROJECT}|g" "$CHART_FILE"  
    fi

    if [[ "${INPUT_EGRESSIP_ALLOCATION,,}" != "none" ]]; then

      # Check and create chart file
      if [ ! -f "$IPPOOL_FILE" ]; then
        log_info "ERROR: Cluster dont have an IP pool file on the required path: $IPPOOL_FILE"
        exit 1
      fi

      export TARGET_SUBNET=$(echo "$INPUT_EGRESSIP_ALLOCATION" | awk -F'[(]' '{print $1}')
      REQUESTED_SUBNET_IPs=$(echo "$INPUT_EGRESSIP_ALLOCATION" | awk -F'[()]' '{print $2}')
      AVAILABLE_IPS=$(yq -r '.[] | select(.subnet == strenv(TARGET_SUBNET)) | .ips[] | select(.status == "available") | .ip' "$IPPOOL_FILE" | head -n "$REQUESTED_SUBNET_IPs")
      FOUND_COUNT=$(echo "$AVAILABLE_IPS" | wc -w)

      # Fail if we dont have IPs in the pool
      if [ "$FOUND_COUNT" -lt "$REQUESTED_SUBNET_IPs" ]; then
        log_info "Error: Pool file check. Not enough available IPs in subnet $TARGET_SUBNET. Requested: $REQUESTED_SUBNET_IPs, Found: $FOUND_COUNT, Check the pool file on this path  $IPPOOL_FILE"
        exit 1
      fi

      # Create a new object on .dcs-egress.egressIPResources
      yq -i '.dcs-egress.egressIPResources += [{"name": strenv(EGRESSIP_NAME), "egressIPs": [], "namespaceSelector": {"matchLabels": {"dcs.zzz.com/egressip_name": strenv(EGRESSIP_NAME)}}}]' "$VALUES_FILE"

      # Loop IPs logic
      for IP in $AVAILABLE_IPS; do
        export TARGET_IP="$IP"

        # Update the specific IP's status to "allocated" and set the tenant
        yq -i '(.[] | select(.subnet == strenv(TARGET_SUBNET)).ips[] | select(.ip == strenv(TARGET_IP))) |= (.status = "allocated" | .object = strenv(EGRESSIP_NAME))' "$IPPOOL_FILE"
        log_info "Successfully allocated IP: $TARGET_IP  egressip object name $EGRESSIP_NAME"
        # Add IP to a specific egressIPs object list 
        yq -i '(.dcs-egress.egressIPResources[] | select(.name == strenv(EGRESSIP_NAME)).egressIPs) += [strenv(TARGET_IP)]' "$VALUES_FILE"
      done

    fi
    echo "---------------------------------------------------------------------------"
    echo "                             Egress Details                                "
    echo "---------------------------------------------------------------------------"
    echo "Customer/Tenant:                        $TENANT_NAME"
    echo "EgressIP name:                          $EGRESSIP_NAME"
    echo "Cluster:                                $INPUT_TARGET_CLUSTER"
    echo "Lifecycle:                              $INPUT_LIFECYCLE"
    echo "Cost Center:                            $INPUT_COST_CENTER"
    echo "Req Time:                               $REQUESTED_TIMESTAMP"
    echo "Prov Time:                              $PROVISION_TIMESTAMP"
    echo "---------------------------------------------------------------------------"
    echo "                             Project Paths                                 "
    echo "---------------------------------------------------------------------------"
    echo "Project Directory:                      $PROJECT_DIR"
    echo "Project Values File:                    $VALUES_FILE"
    echo "Project Chart File:                     $CHART_FILE"
    echo "Project Helmignore File:                $HELMIGNORE_FILE"
    echo "Tenant Metadata File:                   $TENANT_METADATA_FILE"
    echo "---------------------------------------------------------------------------"
}

function sync_cross_namespace_policies() {
    echo "==========================================================================="
    echo "                 Synchronizing Cross-Namespace Policies                    "
    echo "==========================================================================="
    log_info "Checking for tenant-wide policy dependencies..."

    # Skip if this is a CSO creation, as it doesn't affect tenant namespaces directly
    if [[ "${INPUT_CREATE_CSO,,}" == "true" ]]; then
        log_info "CSO creation. Skipping cross-namespace sync."
        return
    fi

    # 1. Find all CloudNativePG namespaces
    local HAS_PG="false"
    local PG_NAMESPACES=()
    for val_file in $(find "$CUSTOMER_DIR" -mindepth 2 -maxdepth 2 -name "values.yaml"); do
        local project_name=$(basename $(dirname "$val_file"))
        local is_pg=$(yq e '.dcs-namespace-provisioner.managedServices.cloudNativePG.enabled' "$val_file" 2>/dev/null || echo "false")
        if [[ "${is_pg,,}" == "true" ]]; then
            PG_NAMESPACES+=("$project_name")
            HAS_PG="true"
        fi
    done

    # 2. Find all DevSpace namespaces
    local HAS_DEVSPACE="false"
    local DEVSPACES=()
    for dir in "$CUSTOMER_DIR"/dcsc-ds-*; do
        if [ -d "$dir" ]; then
            DEVSPACES+=("$(basename "$dir")")
            HAS_DEVSPACE="true"
        fi
    done

    log_info "CloudNativePG presence: $HAS_PG (Count: ${#PG_NAMESPACES[@]})"
    log_info "DevSpace presence: $HAS_DEVSPACE (Count: ${#DEVSPACES[@]})"

    # 3. Determine Matrix boolean
    local ALLOW="false"
    if [[ "$HAS_PG" == "true" && "$HAS_DEVSPACE" == "true" ]]; then
        ALLOW="true"
    fi

    # Prepare yq array strings (e.g., ["ns1", "ns2"])
    local YQ_DEVSPACE_ARR="[]"
    if [[ ${#DEVSPACES[@]} -gt 0 ]]; then
        local formatted_arr=""
        for ds in "${DEVSPACES[@]}"; do
            formatted_arr="${formatted_arr}\"$ds\", "
        done
        formatted_arr="${formatted_arr%, }"
        YQ_DEVSPACE_ARR="[${formatted_arr}]"
    fi

    local YQ_PG_ARR="[]"
    if [[ ${#PG_NAMESPACES[@]} -gt 0 ]]; then
        local formatted_arr=""
        for pg in "${PG_NAMESPACES[@]}"; do
            formatted_arr="${formatted_arr}\"$pg\", "
        done
        formatted_arr="${formatted_arr%, }"
        YQ_PG_ARR="[${formatted_arr}]"
    fi

    # 4. Sync the new structure to all values.yaml files in the tenant
    for val_file in $(find "$CUSTOMER_DIR" -mindepth 2 -maxdepth 2 -name "values.yaml"); do
        local project_name=$(basename $(dirname "$val_file"))
        
        local IS_CURRENT_DEVSPACE="false"
        if [[ "$project_name" == dcsc-ds-* ]]; then
            IS_CURRENT_DEVSPACE="true"
        fi

        local IS_CURRENT_PG="false"
        for pg_ns in "${PG_NAMESPACES[@]}"; do
            if [[ "$pg_ns" == "$project_name" ]]; then
                IS_CURRENT_PG="true"
                break
            fi
        done

        # Clean up all cross-namespace policy keys first to ensure a clean state
        # (This safely removes them if a feature was turned off, or if we need to swap keys)
        yq e -i "
          del(.dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.cnpgEnabledNamespaces) |
          del(.dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.allowDevspaceEgressToDB) |
          del(.dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.devspaceNamespaces) |
          del(.dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.allowCnpgIngressFromDevSpace)
        " "$val_file"

        # Inject DevSpace specific keys
        if [[ "$IS_CURRENT_DEVSPACE" == "true" ]]; then
            log_info "Syncing cross-namespace policies (DevSpace) for: $project_name"
            yq e -i "
              .dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.cnpgEnabledNamespaces = ${YQ_PG_ARR} |
              .dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.allowDevspaceEgressToDB = ${ALLOW}
            " "$val_file"
        fi

        # Inject CloudNativePG specific keys
        if [[ "$IS_CURRENT_PG" == "true" ]]; then
            log_info "Syncing cross-namespace policies (CloudNativePG) for: $project_name"
            yq e -i "
              .dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.devspaceNamespaces = ${YQ_DEVSPACE_ARR} |
              .dcs-namespace-provisioner.allowedFlows.crossNamespacePolicies.allowCnpgIngressFromDevSpace = ${ALLOW}
            " "$val_file"
        fi
    done
    
    log_info "Cross-namespace policy sync complete."
}

function run_git_ops() {
    log_info "Checking for actual configuration changes..."
    
    # 1. Build the list of paths to check
    local CHECK_PATHS="$CUSTOMER_DIR"
    if [ -f "$IPPOOL_FILE" ]; then
        CHECK_PATHS="$CHECK_PATHS $IPPOOL_FILE"
    fi

    # 2. Check git status. We grep -v (exclude) the metadata file from the diff.
    # If the output is empty, it means no real files were modified.
    local CHANGES
    CHANGES=$(git status --porcelain $CHECK_PATHS | grep -v "/tenant-metadata.yaml$" || true)

    if [ -z "$CHANGES" ]; then
        echo "==========================================================================="
        log_error "No actual configuration changes detected for $TENANT_PROJECT."
        log_error "Pipeline run aborted to avoid creating empty Merge Requests."
        echo "==========================================================================="
        exit 1
    fi

    # 3. Proceed with Git operations since real changes exist
    log_info "Changes detected. Committing..."
    git config --global user.email "${GITLAB_USER_EMAIL}"
    git config --global user.name "${GITLAB_USER_NAME}"
    git checkout -b "$NEW_BRANCH_NAME"
    
    git add "$CUSTOMER_DIR"
    
    if [ -f "$IPPOOL_FILE" ]; then
        git add "$IPPOOL_FILE"
    fi
    
    git commit -m "feat: Scaffold/Update project $TENANT_PROJECT for customer $TENANT_NAME"
    git push "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME"    
    echo ""
    log_info " A new branch '$NEW_BRANCH_NAME' has been pushed."
    echo ""
    echo "---------------------------------------------------------------------------"
    echo "| **  Please create a Merge Request from this branch to continue.   **    |"
    echo "---------------------------------------------------------------------------"
}

# --- Main Execution Flow ---
enable_debug_if_requested

# validate_inputs used to run here. load-payload.sh has already done that work,
# against request-schema.yaml, at the moment this file was sourced.
prepare_variables
sanity_checks
update_metadata

if [[ "${INPUT_CREATE_CSO,,}" == "true" ]]; then
  run_scaffold_cso
else
  run_scaffold_project
fi
validate_security_policies
sync_cross_namespace_policies
run_git_ops
