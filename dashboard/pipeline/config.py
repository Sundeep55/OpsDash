"""Where pipeline requests go, and whether the feature is available at all."""
import os


class PipelineSettings:
    """Connection details for the pipeline project, read from the environment.

    Deliberately separate from GitLabSettings in gitops/fetcher.py even though
    they overlap. Those point at dcs-customer-instances, the repository the
    dashboard *reads*. This points at the repository that owns the pipeline and
    request-schema.yaml. They are usually two different projects, and conflating
    them means a dashboard that reads one repo and triggers pipelines in it by
    accident.

    The URL and SSL setting default to the sync's, because in practice both
    projects live on the same GitLab.
    """

    def __init__(self, env=None):
        env = env if env is not None else os.environ

        # ------------------------------------------------------------ dry run
        # A local schema file instead of a GitLab project, and triggers that are
        # logged rather than sent. For working on the form itself: the whole
        # point of the dialog is the schema-driven rendering, the picklists and
        # the conditional fields, and none of that needs a GitLab to exercise.
        #
        # Set PIPELINE_SCHEMA_FILE to a path and the feature turns on with no
        # project, no token and no network. Nothing can reach GitLab in this
        # mode -- see trigger.py, which returns before building a request.
        self.schema_file = env.get('PIPELINE_SCHEMA_FILE', '').strip()

        self.url = (env.get('PIPELINE_GITLAB_URL') or env.get('GITLAB_URL') or '').rstrip('/')
        self.project_id = env.get('PIPELINE_PROJECT_ID', '')
        self.ref = env.get('PIPELINE_REF', 'main')
        self.token = env.get('PIPELINE_TOKEN', '')

        # Where request-schema.yaml sits inside that project.
        self.schema_path = env.get('PIPELINE_SCHEMA_PATH', 'request-schema.yaml')

        # The schema changes when someone merges a field, which is rare. Long
        # enough that the dashboard is not re-fetching it constantly, short
        # enough that a new field appears the same morning it lands.
        self.schema_ttl_seconds = _int(env.get('PIPELINE_SCHEMA_TTL_SECONDS'), 300)

        self.ssl_verify = (
            env.get('PIPELINE_SSL_VERIFY', env.get('GITLAB_SSL_VERIFY', 'true')).lower() == 'true'
        )

        # Off unless explicitly turned on. A half-configured install should show
        # no trigger buttons rather than buttons that fail when pressed.
        self.enabled = env.get('PIPELINE_ENABLED', 'false').lower() == 'true'

        # Optional Django group gate. Empty means any signed-in user may
        # trigger, which matches how the rest of the dashboard is scoped --
        # everyone who can log in can already read everything.
        self.allowed_group = env.get('PIPELINE_ALLOWED_GROUP', '').strip()

    @property
    def is_dry_run(self):
        """True when the schema comes from disk and nothing is ever sent."""
        return bool(self.enabled and self.schema_file)

    @property
    def is_configured(self):
        if self.is_dry_run:
            return True
        return bool(self.enabled and self.url and self.project_id and self.token)

    @property
    def unavailable_reason(self):
        """Why triggering is off, for the API to hand to the UI.

        Returned to signed-in operators only, and names no secret value -- just
        which setting is missing, so a misconfigured deploy is diagnosable
        without reading pod logs.
        """
        if not self.enabled:
            return 'PIPELINE_ENABLED is not set to true.'
        if self.schema_file:
            return ''
        missing = [
            name for name, value in (
                ('PIPELINE_GITLAB_URL (or GITLAB_URL)', self.url),
                ('PIPELINE_PROJECT_ID', self.project_id),
                ('PIPELINE_TOKEN', self.token),
            ) if not value
        ]
        if missing:
            return 'Not configured: ' + ', '.join(missing) + '.'
        return ''

    def may_trigger(self, user):
        if not self.allowed_group:
            return True
        return user.groups.filter(name=self.allowed_group).exists()


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
