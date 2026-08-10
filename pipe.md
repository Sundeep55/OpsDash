# GitLab CI Samples (Cleaned & Documented)

> **Note** – The two files are stored in *different* repositories.  
> When a pipeline is triggered from either repo it updates **one** common target repo.  
> The split is only to keep the input definitions separate because GitLab does not allow dynamic changes of the input list based on a user’s selection.

---

## Repo 1 – `gitlab-ci.yml` (Provision / De‑commission)

```yaml
spec:
  inputs:
    REQUEST_ID:
      description: "The unique ITSM Request ID associated with this provisioning task."
      default: "<MASKED_REQUEST_ID>"
    REQUESTER_EMAIL:
      description: "The primary email address of the project owner or requester."
      default: "<MASKED_EMAIL>"
    REQUESTED_TIMESTAMP:
      description: "The official provision request time from the ITSM ticket DD/MM/YYYY HH:MM:SS."
      default: "<MASKED_TIMESTAMP>"
    TENANT_NAME:
      description: "The unique identifier or name of the tenant/customer"
      default: "<MASKED_TENANT_NAME>"
    TENANT_PROJECT:
      description: "The project namespace provided by the customer (e.g., projecta-1). Note: This is automatically generated for DevSpace projects."
      default: "<MASKED_PROJECT_PREFIX>"
    EGRESSIP_SUBNET:
      description: "Select the Subnet and the number of IPs to assign to EgressIP"
      options:
        - "NONE"
        - "x.x.x.x/24(1)IP"
        - "x.x.x.x/24(2)IPs"
      default: "NONE"
    TARGET_CLUSTER:
      description: "The target DCS cluster where the project will be deployed (e.g., managed-cluster)."
      options: ["managed-cluster"]
      default: "managed-cluster"
    SIGLUM:
      description: "The organizational siglum or department code associated with this tenant."
      default: "<MASKED_SIGLUM>"
    COST_CENTER:
      description: "The Billing or WBS code for the project. Leave empty if the project is non‑billable (Required for new tenants only)."
      default: "<MASKED_COST_CENTER>"
    LIFECYCLE:
      description: "The environmental lifecycle stage for this deployment."
      options: ["dev", "prod"]
      default: "dev"
    ARD_LINK:
      description: "In case of **Prod** Namespaces, please specify the url/path to the ARD."
      default: "<MASKED_ARD_URL>"
    ROUTE_EXCEPTION:
      description: "Enable if the tenant owner has requested a security exception to allow ROUTES in dev namespace"
      type: boolean
      default: false
    NAMESPACE_IS_FOR_DEVSPACE:
      description: "Indicates whether the namespace is intended for use as a user DevSpace."
      type: boolean
      default: false
    CSO_CREATE:
      description: "For EgressIP creation CSO (cluster‑scope object) for a specific tenant."
      type: boolean
      default: false
    TENANT_ADD_NS_TO_SERVICE_MESH:
      description: "Determines if the namespace should be integrated into an existing tenant service mesh."
      type: boolean
      default: false
    TENANT_DEPLOY_SERVICE_MESH:
      description: "Specifies whether to deploy a dedicated service mesh instance for this tenant."
      type: boolean
      default: false
    GPU_ENABLED:
      description: "Specifies whether to enable the GPU Node for the tenant."
      type: boolean
      default: false
    GPU_TIERS:
      description: "Select 'standard' for shared access. For dedicated GPUs, select 'xxxx.h200' (full card without partitions)."
      options: ["None", "xxx.h200-01", "xxxx.h200-02"]
      default: "None"
    ARGOCD_OPERATOR_SERVICES:
      description: "Specifies whether to enable the ArgoCD Operator for the tenant."
      type: boolean
      default: false
    GITLAB_OPERATOR_SERVICES:
      description: "Specifies whether to enable the GitLab Operator for the tenant."
      type: boolean
      default: false
    CLOUDNATIVEPG_OPERATOR_SERVICES:
      description: "Specifies whether to enable the CloudNativePG Operator for the tenant."
      type: boolean
      default: false
    CERT_MANAGER_OPERATOR_SERVICES:
      description: "Specifies whether to enable the Cert Manager Operator for the tenant."
      type: boolean
      default: false
    LOKI_OPERATOR_SERVICES:
      description: "Specifies whether to enable the Loki Operator for the tenant."
      type: boolean
      default: false
    DECOMMISSION:
      description: "Specifies whether to decommission the target namespace or project."
      type: boolean
      default: false
    DECOMMISSION_CSO:
      description: "For EgressIP decommission CSO (cluster‑scope object) for a specific tenant."
      type: boolean
      default: false
---

# Include the auto‑update logic (uncomment when needed)
# include:
#   - local: '.gitlab/auto-update.yml'

stages:
  - validate
  - scaffold
  - decommission
  - syncmetadata
  - maintenance

.base-job:
  image: ${HARBOR_URL}/xxx-internal-images/pipeline-tools:1.1.3
  tags:
    - pipeline
  variables:
    TZ: "Europe/Paris"
    GIT_SSL_NO_VERIFY: "true"
    INPUT_REQUESTER_EMAIL: $[[ inputs.REQUESTER_EMAIL ]]
    INPUT_REQUEST_ID: $[[ inputs.REQUEST_ID ]]
    INPUT_REQUESTED_TIMESTAMP: $[[ inputs.REQUESTED_TIMESTAMP ]]
    INPUT_SIGLUM: $[[ inputs.SIGLUM ]]
    INPUT_COST_CENTER: $[[ inputs.COST_CENTER ]]
    INPUT_TENANT_NAME: $[[ inputs.TENANT_NAME ]]
    INPUT_TENANT_PROJECT: $[[ inputs.TENANT_PROJECT ]]
    INPUT_TARGET_CLUSTER: $[[ inputs.TARGET_CLUSTER ]]
    INPUT_LIFECYCLE: $[[ inputs.LIFECYCLE ]]
    INPUT_ARD_LINK: $[[ inputs.ARD_LINK ]]
    INPUT_ADD_NS_TO_MESH: $[[ inputs.TENANT_ADD_NS_TO_SERVICE_MESH ]]
    INPUT_DEPLOY_MESH: $[[ inputs.TENANT_DEPLOY_SERVICE_MESH ]]
    INPUT_NAMESPACE_IS_FOR_DEVSPACE: $[[ inputs.NAMESPACE_IS_FOR_DEVSPACE ]]
    INPUT_ROUTE_EXCEPTION: $[[ inputs.ROUTE_EXCEPTION ]]
    INPUT_CSO_CREATE: $[[ inputs.CSO_CREATE ]]
    INPUT_EGRESSIP_SUBNET: $[[ inputs.EGRESSIP_SUBNET ]]
    INPUT_DECOMMISSION: $[[ inputs.DECOMMISSION ]]
    INPUT_DECOMMISSION_CSO: $[[ inputs.DECOMMISSION_CSO ]]
    INPUT_ARGOCD_OPERATOR_SERVICES: $[[ inputs.ARGOCD_OPERATOR_SERVICES ]]
    INPUT_GITLAB_OPERATOR_SERVICES: $[[ inputs.GITLAB_OPERATOR_SERVICES ]]
    INPUT_CLOUDNATIVEPG_OPERATOR_SERVICES: $[[ inputs.CLOUDNATIVEPG_OPERATOR_SERVICES ]]
    INPUT_CERT_MANAGER_OPERATOR_SERVICES: $[[ inputs.CERT_MANAGER_OPERATOR_SERVICES ]]
    INPUT_LOKI_OPERATOR_SERVICES: $[[ inputs.LOKI_OPERATOR_SERVICES ]]
    INPUT_GPU_ENABLED: $[[ inputs.GPU_ENABLED ]]
    INPUT_GPU_TIERS: $[[ inputs.GPU_TIERS ]]

validate-mr-permissions:
  stage: validate
  extends: .base-job
  script:
    - chmod +x ./pipeline-scripts/validate-customer-values-file.sh
    - ./pipeline-scripts/validate-customer-values-file.sh
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"

scaffold-tenant:
  stage: scaffold
  extends: .base-job
  script:
    - echo ">>> Scaffolding Mode Selected <<<"
    - chmod +x ./pipeline-scripts/scaffold.sh
    - ./pipeline-scripts/scaffold.sh
  rules:
    - if: '$SYNC_METADATA == "true"'
      when: never
    - if: '($INPUT_DECOMMISSION == "true" || $INPUT_DECOMMISSION_CSO=="true")'
      when: never
    - if: '$CI_PIPELINE_SOURCE == "web"'
    - if: '$CI_PIPELINE_SOURCE == "trigger"'

decommission-tenant:
  stage: decommission
  extends: .base-job
  script:
    - echo ">>> Decommissioning Mode Selected <<<"
    - chmod +x ./pipeline-scripts/decommission.sh
    - ./pipeline-scripts/decommission.sh
  rules:
    - if: '$SYNC_METADATA == "true"'
      when: never
    - if: '$CI_PIPELINE_SOURCE == "web" && ($INPUT_DECOMMISSION == "true" || $INPUT_DECOMMISSION_CSO=="true")'

sync-metadata:
  stage: syncmetadata
  extends: .base-job
  script:
    - echo ">>> Sync Mode Selected <<<"
    - chmod +x ./pipeline-scripts/sync-metadata.sh
    - ./pipeline-scripts/sync-metadata.sh
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web" && $SYNC_METADATA == "true"'
```

### What this CI does

| Stage | Purpose |
|-------|---------|
| **validate** | Checks that the supplied customer values are syntactically correct (run only on merge‑request events). |
| **scaffold** | Generates the tenant/project resources (namespaces, service‑mesh, GPU, operators, etc.) based on the input flags. |
| **decommission** | Tears‑down a tenant or its CSO objects when `DECOMMISSION`/`DECOMMISSION_CSO` is true. |
| **syncmetadata** | Optional step that only runs when the `SYNC_METADATA` flag is set – synchronises metadata between the source and target repos. |
| **maintenance** | Placeholder for any future maintenance jobs. |

All jobs inherit `.base-job`, which defines the Docker image, tags, timezone, and a set of **environment variables** that expose the input values to the scripts.

---

## Repo 2 – `gitlab-ci.yml` (Registry Mirror)

```yaml
spec:
  inputs:
    REQUESTER_EMAIL:
      description: "The primary email address of the requester."
      default: "<MASKED_EMAIL>"
    REQUEST_ID:
      description: "The unique ITSM request ID associated with this mirror request."
      default: "<MASKED_REQUEST_ID>"
    REQUESTED_TIMESTAMP:
      description: "The official provision request time from the ITSM ticket (Format: ISO 8601 YYYY‑MM‑DDTHH:MM:SS)."
      default: "<MASKED_ISO_TIMESTAMP>"
    TENANT_NAME:
      description: "The existing tenant name in dcs‑customer‑instances."
      default: "<MASKED_TENANT_NAME>"
    TARGET_CLUSTER:
      description: "The target DCS cluster where the tenant exists."
      default: "managed-cluster"
      options: ["managed-cluster"]
    REPLICATION_TYPE:
      description: "Whether the replication is external or internal within DCS"
      default: "external"
      options: ["external", "internal", "internal-to-secured"]
    REGISTRY_URL:
      description: "The full URL of the external registry to mirror from"
      default: "<MASKED_REGISTRY_URL>"
    REGISTRY_PROVIDER:
      description: "Type of registry provider for the registry, select harbor when replication type is internal"
      default: "docker-registry"
      options: ["docker-registry","docker-hub","harbor","jfrog"]
    REGISTRY_AUTH:
      description: "Whether authentication is required for the external registry."
      type: boolean
      default: false
    REGISTRY_USERNAME:
      description: "The username (accessId) for the external registry (required if REGISTRY_AUTH is true)"
      default: "<MASKED_USERNAME>"
    REGISTRY_SECRET_REF:
      description: "The name of the k8s secret containing registry credentials (required if REGISTRY_AUTH is true)."
      default: "<MASKED_SECRET_REF>"
    HARBOR_PROJECT:
      description: "The Harbor project to replicate images into."
      default: "<MASKED_HARBOR_PROJECT>"
    IMAGE_NAME:
      description: "The image path to replicate. You can pass multiple images separated by commas (e.g., library/nginx, myproject/myapp)."
      default: "<MASKED_IMAGE_PATH>"
    IMAGE_TAG:
      description: "The image tag. Leave empty to replicate all tags. If you provide a single tag, it will apply to all images in the list."
      default: "latest"
---

stages:
  - scaffold-mirror

.base-job:
  image: ${HARBOR_URL}/xxx-internal-images/pipeline-tools:1.1.3
  tags:
    - pipeline
  variables:
    TZ: "Europe/Paris"
    GIT_SSL_NO_VERIFY: "true"
    INPUT_TENANT_NAME: $[[ inputs.TENANT_NAME ]]
    INPUT_TARGET_CLUSTER: $[[ inputs.TARGET_CLUSTER ]]
    INPUT_REPLICATION_TYPE: $[[ inputs.REPLICATION_TYPE ]]
    INPUT_REGISTRY_URL: $[[ inputs.REGISTRY_URL ]]
    INPUT_REGISTRY_PROVIDER: $[[ inputs.REGISTRY_PROVIDER ]]
    INPUT_REGISTRY_AUTH: $[[ inputs.REGISTRY_AUTH ]]
    INPUT_REGISTRY_USERNAME: $[[ inputs.REGISTRY_USERNAME ]]
    INPUT_REGISTRY_SECRET_REF: $[[ inputs.REGISTRY_SECRET_REF ]]
    INPUT_HARBOR_PROJECT: $[[ inputs.HARBOR_PROJECT ]]
    INPUT_IMAGE_NAME: $[[ inputs.IMAGE_NAME ]]
    INPUT_IMAGE_TAG: $[[ inputs.IMAGE_TAG ]]
    INPUT_REQUESTER_EMAIL: $[[ inputs.REQUESTER_EMAIL ]]
    INPUT_REQUEST_ID: $[[ inputs.REQUEST_ID ]]
    INPUT_REQUESTED_TIMESTAMP: $[[ inputs.REQUESTED_TIMESTAMP ]]

scaffold-registry-mirror:
  stage: scaffold-mirror
  extends: .base-job
  script:
    - echo ">>> Registry Mirror Scaffolding Mode <<<"
    - chmod +x ./pipeline-scripts/scaffold-registry-mirror.sh
    - ./pipeline-scripts/scaffold-registry-mirror.sh
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'
    - if: '$CI_PIPELINE_SOURCE == "trigger"'
```

### What this CI does

| Stage | Purpose |
|-------|---------|
| **scaffold‑mirror** | Creates (or updates) the Kubernetes resources needed to mirror a container image registry into the internal Harbor instance. The job supports both **external** (e.g., Docker Hub) and **internal** (Harbor) replication types. |
| **Variables** | All inputs are exposed as `INPUT_*` variables so the `scaffold-registry-mirror.sh` script can read them. Authentication credentials are passed via a Kubernetes secret reference when `REGISTRY_AUTH` is true. |

---

## 📚 Summary of the Two Pipelines

| Repo | Main Goal | Typical Triggers |
|------|-----------|------------------|
| **Repo 1** | Provision, update, or de‑commission a tenant/project (including optional services like GPU, service‑mesh, ArgoCD, etc.). | `web` UI run, `trigger` from another pipeline, or a merge‑request validation. |
| **Repo 2** | Mirror container images from an external registry into an internal Harbor project. | `web` UI run or `trigger` from another pipeline. |

Both pipelines **target the same downstream repository** that holds the actual Terraform/K8s manifests (or other IaC artefacts). By separating the input definitions:

* **Repo 1** focuses on tenant‑level configuration.  
* **Repo 2** focuses on registry‑mirroring configuration.

This separation sidesteps GitLab’s limitation that a single `.gitlab-ci.yml` cannot change its `spec.inputs` list dynamically based on a user’s choice. Each repo can be invoked independently, yet they both feed the same destination, keeping the overall workflow clean and modular.
