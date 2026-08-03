"""Chart.yaml -- the chart's declared dependencies.

For most namespaces this is a single entry, the namespace-provisioner chart
that creates the namespace and configures quotas, Harbor and network policy.
"""
from dashboard.models import HelmDeployment


def parse_chart(payload, ctx):
    if ctx.namespace is None:
        return

    for dep in payload.get('dependencies', []):
        deployment, _ = HelmDeployment.objects.update_or_create(
            namespace=ctx.namespace,
            chart_name=dep.get('name', 'Unknown'),
            defaults={'version': dep.get('version', 'Unknown')},
        )
        ctx.state.active_helm_ids.add(deployment.id)
