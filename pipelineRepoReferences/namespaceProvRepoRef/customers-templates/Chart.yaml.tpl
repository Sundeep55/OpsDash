---
apiVersion: v2
name: dcs-tenant-instance
description: A Helm chart to generate Customer Resources
type: application
appVersion: "1.0.0"
annotations:
    project: dcs
version: 1.0.0
dependencies:
  - name: dcs-namespace-provisioner
    version: 3.14.0
    repository: oci://__HARBOR_URL__/__HARBOR_OCI_PROJECT__
  - name: dcs-service-mesh
    version: 2.0.2
    repository: oci://__HARBOR_URL__/__HARBOR_OCI_PROJECT__
maintainers:
  - name: Country specific Ops
    email: country-ops@zzz.com
