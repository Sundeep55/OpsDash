"standard":
  dcs-namespace-provisioner:
    requiredLabels:
      gpu-access: "enabled"
      gpu-tier: "gpu-standard"
    gpuConfig:
      enabled: true
      type: "full"
      gpuCount: "1"
      limitRange:
        min: 1
        max: 2
    resourceQuota:
      limitsCpu: "32"
      limitsMemory: "64Gi"
    limitRange:
      containerCPU: "4"
      containerRAM: "8Gi"

"dedicated.h200.1g.18gb":
  dcs-namespace-provisioner:
    requiredLabels:
      gpu-access: "enabled"
      gpu-tier: "dedicated.h200"
    gpuConfig:
      enabled: true
      type: "mig"
      gpuCount: "1"
      profile: "1g.18gb"
    resourceQuota:
      limitsCpu: "32"
      limitsMemory: "128Gi"
    limitRange:
      containerCPU: "8"
      containerRAM: "16Gi"

"dedicated.h200":
  dcs-namespace-provisioner:
    requiredLabels:
      gpu-access: "enabled"
      gpu-tier: "dedicated.h200"
    gpuConfig:
      enabled: true
      type: "full"
      gpuCount: "8"
    resourceQuota:
      limitsCpu: "32"
      limitsMemory: "128Gi"
    limitRange:
      containerCPU: "8"
      containerRAM: "16Gi"
