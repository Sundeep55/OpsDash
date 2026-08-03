from dataclasses import dataclass, field


@dataclass
class SyncState:
    """Mutable state threaded through a single sync run.

    The active_* collections drive the prune in reconciler.py: anything not
    recorded here during the walk is absent from Git and gets deleted, so a
    parser that creates a record must also register it.
    """

    active_cr_ids: set = field(default_factory=set)
    active_helm_ids: set = field(default_factory=set)
    active_namespace_names: set = field(default_factory=set)
    active_tenant_names: set = field(default_factory=set)

    # Namespaces whose route exception was granted by tenant-metadata.yaml.
    # The provisioner parser must not overwrite those. This works because
    # os.walk yields a tenant directory's own files before descending into its
    # namespace subdirectories, so tenant metadata is always seen first.
    tenant_route_exceptions: set = field(default_factory=set)

    # Namespaces that at least one parser wrote configuration for. Reported at
    # the end of the run.
    configured_namespaces: set = field(default_factory=set)

    def record_namespace(self, name):
        self.active_namespace_names.add(name)

    def record_configured(self, namespace):
        if namespace is not None:
            self.configured_namespaces.add(namespace.name)
