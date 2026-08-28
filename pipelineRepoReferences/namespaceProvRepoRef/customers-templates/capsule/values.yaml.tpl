---
dcs-tenant-provisioner:
  tenantName: "__TENANT_PROJECT__"

  # Required labels and annotations for the Kubernetes Resources
  requiredLabels:
    dcs.airbus.com/tenant_name: "__TENANT_NAME__"
    dcs.airbus.com/sub_tenant_name: "__TENANT_PROJECT__"
    dcs.airbus.com/target_cluster: "__TARGET_CLUSTER__"
    dcs.airbus.com/managed_cluster: "true"
    dcs.airbus.com/lifecycle: "__LIFECYCLE__"
    app: "__APP_LABEL__"
    siglum: "__SIGLUM__"

  # Optional labels and annotations for the Kubernetes Resources
  additionalLabels:
    cost_center: "__COST_CENTER__"

  # Optional labels and annotations for the Kubernetes Resources
  additionalAnnotations:
    tenant_owner: "__CONTACT_PERSON__"

  routeException:
    enabled: false

  # Project owner group and role manage
  project_owner_config:
    project_owner:
      initialUsers:
        - __REQUESTER_EMAIL__

  gpuConfig:
    enabled: false

  globalEgressIpName: dcsc-ei-__TENANT_PROJECT__

  managedNamespaces: []

  # Project user group and role manage
  project_user_config:
    project_users:
      initialUsers: []

  networkPolicy:
    egressip: []
    # - name: usecase1
    #   podSelectorLabels:
    #     app: my-app
    #     tier: frontend
    #   egressIpLabel: "dcsc-springfield-atom"
    #   rules:
    #     - cidr: "10.117.178.32/32"
    #       ports:
    #         - port: 8080
    #           protocol: TCP
    #         - port: 5432
    #           protocol: TCP
    # - name: usecase2
    #   podSelectorLabels: {}
    #   egressIpLabel: "dcsc-ei-umbrella-corp"
    #   rules:
    #     - cidr: "1.2.3.4/32"
    #       ports:
    #         - port: 443
    #           protocol: TCP

  # Manage group namespaces communication
  allowedFlows:
    enabled: false
    connections: []

  # Default resources quotas for Namespace
  resourceQuota:
    enabled: true
    limitsCpu: "16"
    requestsCpu: "1"
    limitsMemory: "64Gi"
    requestsMemory: "1000Mi"
    requestsEphemeralStorage: "50Gi"
    requestsStorage: "100Gi"

  # Default storage limit range for Namespace
  # Manage the max and min amount of resources container/pod can use
  limitRange:
    storageMax: "25Gi"
    storageMin: "1Gi"

  retentionPolicy:
    enable: true
    # Runs weekly at 1:00 AM
    schedule: "0 0 1 * * 0"

    # Rule 1: Always retain specific tags (e.g., prod, latest, main)
    alwaysRetainTags: ""

    # Rule 2: Retain images pulled within the last X days
    daysSinceLastPullProd: 90
    daysSinceLastPullDev: 30

  # Manage customer group and repository in Harbor registry
  harborOnboardingConfig:
    registryUrl: registry.dcs.aircloud.common.airbusds.corp
    enable: true
    keyCloakDcsRealmConfig:
      realmName: dcs
      identityProviderName: csso
    autoSbomGeneration: true
    storageQuota: 50
    vulnerabilityScanning: true
    enableContentTrust: false
    enableContentTrustCosign: false
    forceDestroy: false

  harborRobotAccounts: # Manage Harbor registry Robot account
    enabled: false
    robotAccounts:
      - nameSuffix: account
        description: ""
        default: true # Permission set base on lifecycle tag
        enablePullSecret: false # Enable automatic generation of imagePullSecrets in Tenant namespaces using this account

#      - nameSuffix: cicd # MyITSM Request
#        description: ""
#        default: false # Define list of permission; for PROD validation will remove any PUSH permission
#        permissions:
#          - resource: "repository"
#            action: "pull"
#          - resource: "repository"
#            action: "push"
#          - resource: "repository"
#            action: "list"
#          - resource: "tag"
#            action: "list"
#          - resource: "artifact"
#            action: "read"
#          - resource: "scan"
#            action: "read"
#          - resource: "artifact"
#            action: "list"
