"""The boundary check, and the POST to GitLab.

WHAT IS CHECKED HERE, AND WHAT IS NOT
-------------------------------------
This is not a third copy of the validation rules. request-schema.yaml declares
them once; static/js/lib/schema-form.js applies them in the browser so an
operator finds out about a mistake while typing, and
pipeline-scripts/load-payload.sh enforces them as the real gate. Re-implementing
show_if, required_if, normalise and the type rules in Python would be a third
implementation to keep in step, and the one place they could disagree silently.

What this does check is a different question: not "is this request sensible" but
"is this request shaped like something we are willing to forward under our
token". A browser can send anything; the dashboard holds a credential the
operator does not; so the payload is checked for shape and provenance before it
travels. A request that passes here and is nonsense still fails in the shim,
loudly, which is where it should fail.

Concretely: the operation must be one the schema declares, every key must be a
field that operation offers, values must be scalars, and the whole thing must
fit. Nothing else.
"""
import json
import logging
import urllib.parse

import requests
import urllib3

from .config import PipelineSettings
from .schema import get_schema

logger = logging.getLogger(__name__)

TRIGGER_TIMEOUT = (5, 20)

# The payload travels as a single CI input value. Every fixed-size request
# measures under 800 bytes; only a registry mirror grows, because its image list
# is comma-separated and unbounded. 64 KB is far above anything real and well
# under any limit GitLab imposes.
MAX_PAYLOAD_BYTES = 64 * 1024


class TriggerRejected(ValueError):
    """The request was refused before anything left the process."""


class TriggerFailed(RuntimeError):
    """GitLab was asked and said no, or could not be reached."""


def check_payload(operation, payload, schema):
    """Shape and provenance. Returns the payload as strings, or raises.

    Values are coerced to strings because that is what the CI input carries and
    what load-payload.sh reads; a JSON `true` and the string "true" must not
    reach the pipeline as two different things.
    """
    operations = schema.get('operations') or {}
    if operation not in operations:
        raise TriggerRejected(
            f'"{operation}" is not an operation this pipeline offers.'
        )

    if not isinstance(payload, dict):
        raise TriggerRejected('The request payload must be a JSON object.')

    allowed = set((operations[operation] or {}).get('fields') or [])
    declared = set((schema.get('fields') or {}).keys())

    clean = {}
    for key, value in payload.items():
        if key not in allowed:
            # Two different mistakes, worth two different messages: a field that
            # exists but belongs to another operation is a UI bug; one that does
            # not exist at all is a stale client or something hand-rolled.
            if key in declared:
                raise TriggerRejected(f'"{key}" is not accepted by operation "{operation}".')
            raise TriggerRejected(f'"{key}" is not a field declared in the schema.')

        if isinstance(value, bool):
            # Before the numeric check: bool is a subclass of int in Python, so
            # `True` would otherwise stringify as "True" rather than "true" and
            # fail every `[[ "$x" == "true" ]]` in the scripts.
            clean[key] = 'true' if value else 'false'
        elif value is None:
            continue
        elif isinstance(value, (str, int, float)):
            clean[key] = str(value)
        else:
            raise TriggerRejected(
                f'"{key}" must be a string, number or boolean, not {type(value).__name__}.'
            )

    encoded = json.dumps(clean, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > MAX_PAYLOAD_BYTES:
        raise TriggerRejected(
            f'The request is {len(encoded)} bytes, over the {MAX_PAYLOAD_BYTES} byte limit.'
        )
    return clean, encoded


def trigger(operation, payload, triggered_by, settings=None):
    """Start a pipeline. Returns GitLab's response dict.

    `triggered_by` is set by the view from the signed-in user and is never taken
    from the request body -- the point of it is that the client cannot choose it.
    """
    settings = settings or PipelineSettings()
    if not settings.is_configured:
        raise TriggerFailed(settings.unavailable_reason or 'Pipeline triggering is not configured.')

    schema = get_schema(settings)
    _, encoded = check_payload(operation, payload, schema)

    if not settings.ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = (f"{settings.url}/api/v4/projects/"
           f"{urllib.parse.quote(str(settings.project_id), safe='')}/pipeline")

    body = {
        'ref': settings.ref,
        'inputs': {
            'OPERATION': operation,
            'REQUEST_PAYLOAD': encoded,
            # Attribution. The pipeline runs as the service token, so without
            # this every request in GitLab looks like it came from the same bot.
            # Deliberately not requester_email: that is the customer who raised
            # the ITSM ticket, not whoever pressed the button here.
            'TRIGGERED_BY': triggered_by or '',
        },
    }

    # Logged before the call, not after: if GitLab times out we still want a
    # record that this user asked for this operation. The payload itself is not
    # logged -- it carries requester addresses and cost centres.
    logger.info(
        "Pipeline trigger: operation=%s project=%s ref=%s by=%s",
        operation, settings.project_id, settings.ref, triggered_by,
    )

    try:
        response = requests.post(
            url,
            json=body,
            headers={'PRIVATE-TOKEN': settings.token},
            timeout=TRIGGER_TIMEOUT,
            verify=settings.ssl_verify,
        )
    except requests.RequestException as exc:
        raise TriggerFailed(f"Could not reach GitLab: {exc}") from exc

    if response.ok:
        try:
            return response.json()
        except ValueError as exc:
            raise TriggerFailed("GitLab accepted the request but returned no pipeline.") from exc

    # GitLab's own message is the useful part -- "there can not be more than 20
    # inputs", "insufficient permissions", a `rules:` mistake. Pass it through
    # rather than flattening it to "trigger failed".
    detail = ''
    try:
        body = response.json()
        detail = body.get('message') or body.get('error') or ''
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail)
    except ValueError:
        detail = (response.text or '')[:400]

    raise TriggerFailed(f"GitLab refused the request ({response.status_code}): {detail}".strip())
