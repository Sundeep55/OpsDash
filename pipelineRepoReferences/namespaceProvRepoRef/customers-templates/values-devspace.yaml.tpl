dcs-namespace-provisioner:

  devspaceConfig:
    isDevspace: __NAMESPACE_IS_FOR_DEVSPACE__
    devspaceUser: __REQUESTER_EMAIL__

  project_owner_config:
    owner_rbac_enable: true
    project_owner:
      initialUsers:
        - __REQUESTER_EMAIL__

  resourceQuota:
    limitsCpu: "5"
    requestsCpu: "3"
    limitsMemory: "9Gi"
    requestsMemory: "4Gi"
    requestsEphemeralStorage: "15Gi"
    requestsStorage: "15Gi"

  limitRange:
    storageMax: "20Gi"

  harborOnboardingConfig:
    enable: false
  
  harborRobotAccounts:
    enabled: false
  
  allowedFlows:
    proxyEnabled: true
