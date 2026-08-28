"""Raw manifests under a namespace's templates/ directory.

Most charts are empty and carry only the namespace-provisioner dependency. A
templates/ directory means the customer needed something extra -- a CRD, a
security exception, cluster-wide permissions -- so these are stored verbatim
for display rather than interpreted.
"""
import yaml

from dashboard.models import CustomResource


def parse_templates(content, ctx):
    """Store every document in a multi-document manifest as a CustomResource.

    Documents without both a kind and metadata are not Kubernetes objects and
    are skipped.
    """
    owner = ctx.namespace or getattr(ctx, 'capsule', None)
    if owner is None:
        return

    for doc in yaml.safe_load_all(content):
        if not doc or 'kind' not in doc or 'metadata' not in doc:
            continue

        cr, _ = CustomResource.objects.update_or_create(
            namespace=ctx.namespace,
            capsule=getattr(ctx, 'capsule', None),
            kind=doc['kind'],
            name=doc['metadata'].get('name', 'unknown'),
            defaults={'content': yaml.dump(doc, default_flow_style=False)},
        )
        ctx.state.active_cr_ids.add(cr.id)
