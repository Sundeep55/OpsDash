"""request-schema.yaml, fetched from the pipeline project and cached.

Fetched rather than vendored on purpose. The schema is the single declaration of
every field the pipeline accepts, and it lives in the repository that owns the
pipeline. A copy inside this image would be a copy that goes stale the moment
someone merges a field -- and the form would then be missing it with nothing to
say so. Reading it live means adding a field to the schema makes it appear in
the dashboard with no OpsDash release at all.

The cost is a dependency on that project being reachable. That is handled by
degrading rather than failing: a schema that cannot be fetched means the trigger
buttons do not appear, and the GitLab Pages form -- which is the primary route
anyway -- is unaffected.
"""
import logging
import threading
import time
import urllib.parse

import requests
import urllib3
import yaml

from .config import PipelineSettings

logger = logging.getLogger(__name__)

# (connect, read). Short: this runs inside a request the operator is waiting on,
# so a hung GitLab must not hold a gunicorn worker open.
FETCH_TIMEOUT = (5, 15)

# Refuse to parse anything absurd. The real file is around 20 KB; this only
# guards against a redirect to something else entirely.
MAX_SCHEMA_BYTES = 2 * 1024 * 1024


class SchemaUnavailable(RuntimeError):
    """The schema could not be fetched or parsed. Carries an operator-readable
    reason, since the UI shows it in place of the trigger buttons."""


class _Cache:
    """One entry, guarded by a lock.

    The lock is not about correctness -- a duplicated fetch would be harmless --
    but gunicorn runs threads, and without it every thread that arrives during a
    slow fetch starts its own.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None
        self._fetched_at = 0.0

    def get(self, settings, force=False):
        with self._lock:
            age = time.time() - self._fetched_at
            fresh = self._value is not None and age < settings.schema_ttl_seconds
            if fresh and not force:
                return self._value

            try:
                value = _fetch(settings)
            except SchemaUnavailable as exc:
                # Serve a stale copy rather than nothing. A GitLab blip should
                # not take the trigger buttons away from someone mid-task; the
                # schema changes rarely enough that a few minutes stale is not a
                # meaningful risk.
                if self._value is not None:
                    logger.warning("Schema refresh failed, serving cached copy: %s", exc)
                    return self._value
                raise

            self._value = value
            self._fetched_at = time.time()
            return value

    def invalidate(self):
        with self._lock:
            self._value = None
            self._fetched_at = 0.0


_cache = _Cache()


def _fetch(settings):
    if not settings.is_configured:
        raise SchemaUnavailable(settings.unavailable_reason or 'Pipeline triggering is not configured.')

    if settings.is_dry_run:
        return _read_file(settings.schema_file)

    if not settings.ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # The file path is a path segment, so every '/' has to be percent-encoded --
    # safe='' is what makes quote encode them instead of leaving them alone.
    encoded = urllib.parse.quote(settings.schema_path, safe='')
    url = (f"{settings.url}/api/v4/projects/{urllib.parse.quote(str(settings.project_id), safe='')}"
           f"/repository/files/{encoded}/raw")

    try:
        response = requests.get(
            url,
            params={'ref': settings.ref},
            headers={'PRIVATE-TOKEN': settings.token},
            timeout=FETCH_TIMEOUT,
            verify=settings.ssl_verify,
        )
    except requests.RequestException as exc:
        raise SchemaUnavailable(f"Could not reach GitLab: {exc}") from exc

    if response.status_code == 404:
        raise SchemaUnavailable(
            f"{settings.schema_path} was not found in project {settings.project_id} on ref {settings.ref}."
        )
    if response.status_code in (401, 403):
        raise SchemaUnavailable(
            "GitLab refused the token. It needs read access to the pipeline project."
        )
    if not response.ok:
        raise SchemaUnavailable(f"GitLab answered {response.status_code} for the schema.")

    if len(response.content) > MAX_SCHEMA_BYTES:
        raise SchemaUnavailable("The schema file is implausibly large; refusing to parse it.")

    try:
        parsed = yaml.safe_load(response.content)
    except yaml.YAMLError as exc:
        raise SchemaUnavailable(f"The schema is not valid YAML: {exc}") from exc

    return _validate(parsed, 'The file fetched')


def _validate(parsed, source):
    if not isinstance(parsed, dict) or 'fields' not in parsed or 'operations' not in parsed:
        raise SchemaUnavailable(
            f"{source} does not look like request-schema.yaml "
            "(no 'fields' and 'operations' at the top level)."
        )
    return parsed


def _read_file(path):
    """The schema from a local file, for the dry-run mode.

    Re-read on every cache miss rather than held forever, so editing the schema
    and reloading the page shows the change -- which is the point of pointing at
    a file in the first place.
    """
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError as exc:
        raise SchemaUnavailable(f"Could not read PIPELINE_SCHEMA_FILE at {path}: {exc}") from exc

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SchemaUnavailable(f"{path} is not valid YAML: {exc}") from exc

    return _validate(parsed, path)


def get_schema(settings=None, force=False):
    """The parsed schema, from cache when it is fresh.

    Raises SchemaUnavailable, which callers turn into a 503 rather than a 500:
    the dashboard is fine, this one feature is not.
    """
    return _cache.get(settings or PipelineSettings(), force=force)


def invalidate():
    _cache.invalidate()
