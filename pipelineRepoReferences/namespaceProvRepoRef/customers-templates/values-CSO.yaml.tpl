dcs-egress:
  requiredLabels:
    dcs.airbus.com/tenant_name: "__TENANT_NAME__"
    dcs.airbus.com/target_cluster: "__TARGET_CLUSTER__"
    dcs.airbus.com/lifecycle: "__LIFECYCLE__"
  additionalLabels:
    cost_center: "__COST_CENTER__"
  additionalAnnotations:
    tenant_owner: "__CONTACT_PERSON__"
  egressIPResources: []
