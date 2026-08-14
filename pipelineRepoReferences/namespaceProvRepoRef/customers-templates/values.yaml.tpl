---
dcs-namespace-provisioner:
  project_namespace: "__TENANT_PROJECT__"

  # Required labels and annotations for the Kubernetes Resources
  requiredLabels:
    dcs.zzz.com/tenant_name: "__TENANT_NAME__"
    dcs.zzz.com/tenant_project: "__TENANT_PROJECT__"
    dcs.zzz.com/target_cluster: "__TARGET_CLUSTER__"
    dcs.zzz.com/managed_cluster: "true"
    dcs.zzz.com/lifecycle: "__LIFECYCLE__"
    app: "__APP_LABEL__"
    siglum: "__SIGLUM__"

  # Optional labels and annotations for the Kubernetes Resources
  additionalLabels:
    cost_center: "__COST_CENTER__"
    dcs.zzz.com/egressip_name: "dcsc-ei-__TENANT_NAME__"

  # Optional labels and annotations for the Kubernetes Resources
  additionalAnnotations:
    tenant_owner: "__CONTACT_PERSON__"

  routeException:
    enabled: false

  managedServices:
    argocdOperator:
      enabled: false
    cloudNativePG:
      enabled: false
    gitlabOperator:
      enabled: false
    certManagerOperator:
      enabled: false
    lokiOperator:
      enabled: false
    perconaMongodbOperator:
      enabled: false

  devspaceConfig:
    isDevspace: false
    devspaceUser: ""

  # Project owner group and role manage
  project_owner_config:
    owner_rbac_enable: true
    project_owner:
      initialUsers:
        - __REQUESTER_EMAIL__

  # Project user group and role manage
  project_user_config:
    user_rbac_enable: false
    project_users:
      initialUsers: []

  # Uncomment for EgressIP NetworkPolicy 
  # networkPolicy:
  #   egressip:
  #     - name: usecase-name
  #       podSelectorLabels: {}
  #       rules:
  #         - cidr: "x.x.x.x/32"
  #           ports:
  #             - port: 443
  #               protocol: TCP

  # Manage group namespaces communication
  allowedFlows:
    enabled: false
    dnsResolutionEnabled: true
    connections: []
    s3ConnectionEnabled: true # Enable connection between namespace pods and S3


  # allowedFlows:
  #   enabled: true
  #   Define pod selector; allow to target specific pods
  #   podSelector:
  #     app: my-database

  #   # Enable dns resolution
  #   dnsResolutionEnabled: true
  #   # Enable Poxy communication
  #   proxyEnabled: true
  #   # Define all connections in a central list
  #   connections:
  #     # This allows claim-test-01 to connect to claim-test-02 on port 5432
  #     - from: "claim-test-01"
  #       to: "claim-test-02"
  #       flows:
  #         - protocol: TCP
  #           port: 5432

  #     # Possibility to add multiple group communication:
  #     - from: "claim-test-01"
  #       to: 
  #         - "claim-test-02"
  #         - "claim-test-02-a"
  #         - "claim-test-02-b"
  #       flows:
  #         - protocol: TCP
  #           port: 443

  # Default resources quotas for Namespace
  resourceQuota:
    enabled: true
    limitsCpu: "16"
    requestsCpu: "1000m"
    limitsMemory: "64Gi"
    requestsMemory: "1000Mi"
    requestsEphemeralStorage: "50Gi"
    requestsStorage: "100Gi"
    openshiftImageStorage: "2Gi"

  # Default storage limit range for Namespace
  # Manage the max and min amount of resources container/pod can use
  limitRange:
    storageMax: "25Gi"
    storageMin: "1Gi"
    containerCPU: "500m"
    containerRequestCPU: "100m"
    containerRAM: "512Mi"
    containerRequestRAM: "256Mi"

  # GPU related configuration
  gpuConfig:
    enabled: false
    type: ""
    gpuCount: 0
    profile: ""

  # Manage customer group and repository in Harbor registry
  harborOnboardingConfig:
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
#    cveAllowlist:
#      - "CVE-2023-12345"
#      - "CVE-2024-67890"

  harborRobotAccounts: # Manage Harbor registry Robot account
    enabled: false
    robotAccounts:
      - nameSuffix: account
        description: ""
        default: true # Permission set base on lifecycle tag
#
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
