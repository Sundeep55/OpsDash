---
dcs-registry-config:
  testConfig:
    enableTests: false
  # namespace where the customer's registry secrets live
  namespace: __SECRET_NAMESPACE__

  # Provider config and system config are managed centrally — skip for customer instances
  harborProviderConfig:
    create: false
    name: harbor-provider-config
  systemConfig:
    enabled: false

  # Projects are managed by the namespace provisioner — do not recreate
  projects: []
  groups: []
  robotAccounts: []

  # External registries to mirror from (populated by the pipeline)
  registries: []

  # Replication rules (populated by the pipeline)
  dockerRegistryReplications: []
  dockerHubReplications: []
  redhatReplications: []
