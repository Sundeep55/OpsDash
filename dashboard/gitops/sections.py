"""The registry of `values.yaml` sections.

One list, in one file, naming every block the sync understands. Adding a section
to the GitOps chart means adding an entry here -- and for the common shape, an
entry is all it takes.

A section is "common shape" when it is a config block with a gate key and some
scalar fields mapping onto a model. Those are fully declarative: name the model,
name the field pairs, done. Anything more (a list of children, a dict of
operators, an ordering rule against another section) supplies its own `apply`
callable instead.

Bespoke sections stay in the registry even though the registry does not
implement them. That is the point: the list is the index of what exists, so
nobody has to grep the parser to find out which blocks are handled.

See docs/adding-a-section.md for the end-to-end checklist.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from dashboard.models import GPUAllocation, HarborConfig, ResourceQuota

MISSING = object()


def to_int(value, default=0):
    """Coerce a YAML scalar to int. gpuConfig.gpuCount is quoted in the repo
    ("3"), so int() on the raw value is not safe."""
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def dig(config, path):
    """Read a dotted path out of nested YAML, returning None if any hop is absent."""
    current = config
    for part in path.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


@dataclass(frozen=True)
class Field:
    """One model field and the YAML key it comes from.

    `source` may be dotted ("limitRange.min") for nested blocks. `cast` runs
    only on a value that was actually present, so a missing key yields `default`
    rather than cast(None).
    """
    model_field: str
    source: str
    default: Any = None
    cast: Optional[Callable] = None

    def read(self, config):
        value = dig(config, self.source)
        if value is None:
            return self.default
        return self.cast(value) if self.cast else value


@dataclass(frozen=True)
class Section:
    """A block under `namespace-provisioner:` in a namespace's values.yaml."""

    #: Stable identifier. Also the key the API exposes it under.
    name: str
    #: Human label, used by the docs and the frontend registry.
    title: str
    #: The key in values.yaml.
    yaml_key: str

    #: Declarative form: the model and the fields to fill.
    model: Any = None
    fields: tuple = ()
    #: Values written on every save regardless of YAML (e.g. is_enabled=True).
    constants: dict = field(default_factory=dict)
    #: Key(s) that switch the section on. First one present wins -- the repo
    #: spells Harbor's gate `enable` and everyone else's `enabled`.
    #: None means the section always applies and is never deleted.
    gate: Optional[tuple] = ('enabled',)

    #: Set for sections this file does not implement, naming where they live.
    #: They stay listed so this registry remains the full index of what the
    #: sync understands, even where the shape is too irregular to declare.
    implemented_by: Optional[str] = None

    #: Whether the API should publish this section under `sections` for the
    #: frontend to render generically. False for the sections that already have
    #: bespoke markup on the detail page and their own top-level API key --
    #: publishing those twice would just be duplication.
    auto_render: bool = True

    #: Labels for the generic renderer, keyed by model field. Falls back to a
    #: prettified field name.
    labels: dict = field(default_factory=dict)

    @property
    def is_declarative(self):
        return self.implemented_by is None

    def gate_open(self, config):
        if self.gate is None:
            return True
        for key in self.gate:
            if key in config:
                return bool(config[key])
        return False


def apply_declarative(section, config, ctx):
    """Write (or clear) a declarative section for one namespace."""
    if not section.gate_open(config):
        # Absence is meaningful: the feature was removed from Git, so the row
        # must go rather than linger as ghost state.
        section.model.objects.filter(namespace=ctx.namespace).delete()
        return

    defaults = dict(section.constants)
    for spec in section.fields:
        defaults[spec.model_field] = spec.read(config)

    section.model.objects.update_or_create(namespace=ctx.namespace, defaults=defaults)


# ---------------------------------------------------------------------------
# The registry.
#
# Order matters only where one section reads state another wrote; the sections
# below are independent, so this is display order.
# ---------------------------------------------------------------------------

SECTIONS = (
    Section(
        name='resourceQuota',
        title='Compute Limits',
        auto_render=False,
        yaml_key='resourceQuota',
        model=ResourceQuota,
        fields=(
            Field('requests_cpu', 'requestsCpu'),
            Field('limits_cpu', 'limitsCpu'),
            Field('requests_memory', 'requestsMemory'),
            Field('limits_memory', 'limitsMemory'),
            Field('requests_storage', 'requestsStorage'),
        ),
    ),
    Section(
        name='gpu',
        title='Hardware Acceleration',
        auto_render=False,
        yaml_key='gpuConfig',
        model=GPUAllocation,
        fields=(
            Field('allocation_type', 'type'),
            Field('gpu_count', 'gpuCount', default=0, cast=to_int),
            Field('limit_min', 'limitRange.min'),
            Field('limit_max', 'limitRange.max'),
            Field('limit_default', 'limitRange.default'),
            Field('limit_default_request', 'limitRange.defaultRequest'),
        ),
    ),
    Section(
        name='harbor',
        title='Harbor Registry',
        auto_render=False,
        yaml_key='harborOnboardingConfig',
        model=HarborConfig,
        # The repo spells this gate `enable`, unlike every other section.
        gate=('enable',),
        constants={'is_enabled': True},
        fields=(
            Field('storage_quota_gb', 'storageQuota', default=0),
            Field('vulnerability_scanning', 'vulnerabilityScanning', default=False),
            Field('auto_sbom_generation', 'autoSbomGeneration', default=False),
            Field('cve_allowlist', 'cveAllowlist', default=()),
        ),
    ),

    # --- Irregular shapes, implemented in parsers/. Listed for completeness. --
    Section(
        name='network_flows',
        title='Networking & Routing',
        yaml_key='allowedFlows',
        # Always written, never gated: a namespace with no allowedFlows block
        # still gets a NetworkPolicy row with everything false.
        gate=None,
        implemented_by='parsers.provisioner._apply_network_policy',
    ),
    Section(
        name='routeException',
        title='Route Exception',
        yaml_key='routeException',
        # Must not overwrite a grant that tenant-metadata.yaml already made,
        # so it reads sync state the declarative form has no access to.
        implemented_by='parsers.provisioner._apply_route_exception',
    ),
    Section(
        name='operators',
        title='Platform Operators',
        yaml_key='managedServices',
        # A dict of operator name -> {enabled}, one row each.
        implemented_by='parsers.provisioner._apply_operators',
    ),
    Section(
        name='robotAccounts',
        title='Harbor Robot Accounts',
        yaml_key='harborRobotAccounts',
        # A list of children, replaced wholesale on each sync.
        implemented_by='parsers.provisioner._apply_robot_accounts',
    ),
    Section(
        name='userAccess',
        title='Project Access',
        # Two sibling blocks (project_owner_config, project_user_config) feeding
        # one model, so there is no single yaml_key.
        yaml_key='project_owner_config',
        implemented_by='parsers.users.apply_user_access',
    ),
)

#: Index by name, for lookups from the API layer and tests.
BY_NAME = {section.name: section for section in SECTIONS}


def apply_registered_sections(prov, ctx):
    """Apply every declarative section to one namespace.

    Sections carrying `implemented_by` are skipped: the parser calls those
    directly, because their shape needs code rather than a declaration.
    """
    for section in SECTIONS:
        if not section.is_declarative:
            continue
        apply_declarative(section, prov.get(section.yaml_key) or {}, ctx)


def auto_rendered_sections():
    """Declarative sections the frontend renders from their descriptor alone."""
    return tuple(s for s in SECTIONS if s.is_declarative and s.auto_render)


def describe(section, instance):
    """Serialise one section's stored row for the generic renderer.

    Returns None when the namespace has no row -- the section is absent from
    the API response entirely rather than appearing as an empty card.
    """
    if instance is None:
        return None
    return {
        'title': section.title,
        'fields': [
            {
                'name': spec.model_field,
                'label': section.labels.get(
                    spec.model_field,
                    spec.model_field.replace('_', ' ').title(),
                ),
                'value': getattr(instance, spec.model_field, None),
            }
            for spec in section.fields
        ],
    }
