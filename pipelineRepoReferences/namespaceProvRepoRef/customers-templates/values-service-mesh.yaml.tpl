dcs-namespace-provisioner:
  resourceQuota:
    enabled: true
    limitsCpu: "2"
    requestsCpu: "1"
    limitsMemory: "2Gi"
    requestsMemory: "1Gi"
    requestsEphemeralStorage: "1Gi"
    requestsStorage: "1Gi"
    openshiftImageStorage: "2Gi"
  allowedFlows:
    dnsResolutionEnabled: true

dcs-service-mesh:
  # -- Required
  cluster:
    domain: apps.qa-ocp-rhosp.dcs.otn1-tnt.iaas.aircloud.common.airbusds.corp
  # -- Required. Add all namespaces that will be part of the service mesh.
  dataplane:
    namespaces: []
  # -- Required
  roleBinding:
    dcsc-servicemesh-appviewer:
      - user-group             # template will add the namespace in front of the group like <NS name>-user-group
    dcsc-servicemesh-appeditor:
      - owner-group            # template will add the namespace in front of the group like <NS name>-owner-group
  # -- Required
  cp:
    tenant: __TENANT_NAME__
    namespace: __TENANT_PROJECT__  # control plane namespace
    gw:  # Gateways
      namespaces:
        - name: __TENANT_PROJECT__ # In case if we want Gateway in a different namespace, we have to use a different one here
    kiali:
      name: kiali-__TENANT_NAME__
