dcs-egress:
  requiredLabels:
    dcs.zzz.com/tenant_name: "__TENANT_NAME__"
    dcs.zzz.com/target_cluster: "__TARGET_CLUSTER__"
    dcs.zzz.com/lifecycle: "__LIFECYCLE__"
  additionalLabels:
    cost_center: "__COST_CENTER__"
  additionalAnnotations:
    tenant_owner: "__CONTACT_PERSON__"
  egressIPResources: []
