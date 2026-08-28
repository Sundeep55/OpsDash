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
    active_operator_ids: set = field(default_factory=set)
    active_namespace_names: set = field(default_factory=set)
    active_tenant_names: set = field(default_factory=set)
    #: (cluster, tenant, name) of every directory identified as a capsule in the
    #: first pass. Directory-level, because a capsule's Chart.yaml and templates/
    #: carry nothing that identifies them.
    capsule_dirs: set = field(default_factory=set)
    #: Capsule fields that only tenant-metadata.yaml knows (ticket, requester,
    #: lifecycle), keyed by capsule name. Deferred rather than applied inline
    #: because file order is arbitrary: the metadata file is frequently read
    #: before the capsule's own values.yaml has created the row, and an
    #: order-dependent write silently loses the ticket.
    capsule_metadata: dict = field(default_factory=dict)
    #: Capsules seen this run. Tracked separately from namespaces because they
    #: are a different model living at the same path depth -- a capsule must not
    #: keep a same-named namespace alive, nor be pruned by the namespace sweep.
    active_capsule_names: set = field(default_factory=set)

    # namespace name -> (cluster, tenant) that claimed it during this run.
    # Namespace and tenant names are globally unique by convention, and the
    # schema relies on that: both use a bare name as primary key. Nothing
    # enforces it, so a name claimed twice with different owners would silently
    # overwrite. Recorded here so it can be reported instead.
    namespace_claims: dict = field(default_factory=dict)

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
