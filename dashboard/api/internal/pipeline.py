"""Pipeline triggering: what the form needs, and the trigger itself.

The dashboard is otherwise read-only. These three endpoints are the exception,
and only one of them writes anything -- and what it writes is a request to
GitLab, not a change to the repository or the database.
"""
import logging

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from dashboard.models import Capsule, Namespace, Tenant
from dashboard.pipeline.config import PipelineSettings
from dashboard.pipeline.schema import SchemaUnavailable, get_schema
from dashboard.pipeline.trigger import TriggerFailed, TriggerRejected, trigger

logger = logging.getLogger(__name__)


class PipelineConfigView(generics.GenericAPIView):
    """Whether the trigger UI should appear at all, and where requests go.

    Never includes the token. The project and ref are shown because an operator
    about to start a pipeline should be able to see which project it lands in.
    """
    serializer_class = serializers.Serializer

    @extend_schema(
        description=(
            "Whether pipeline triggering is configured and permitted for the "
            "signed-in user. The UI hides every trigger control when "
            "`enabled` is false."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        settings = PipelineSettings()
        allowed = settings.may_trigger(request.user)
        return Response({
            'enabled': bool(settings.is_configured and allowed),
            'project_id': settings.project_id if settings.is_configured else '',
            'ref': settings.ref,
            'gitlab_url': settings.url if settings.is_configured else '',
            # Two different reasons the buttons are missing, and an operator
            # deserves to know which: nothing is configured, or it is configured
            # and they are not in the group that may use it.
            'reason': (
                '' if settings.is_configured and allowed
                else ('You are not a member of the group permitted to trigger pipelines.'
                      if settings.is_configured else settings.unavailable_reason)
            ),
        })


class PipelineSchemaView(generics.GenericAPIView):
    """request-schema.yaml as JSON, straight from the pipeline project.

    Served rather than bundled so a field merged into the schema shows up in the
    dashboard form without an OpsDash release.
    """
    serializer_class = serializers.Serializer

    @extend_schema(
        description=(
            "The onboarding request schema -- every operation, the fields it "
            "accepts, and the rules for each -- fetched from the pipeline "
            "project and cached briefly. 503 when it cannot be fetched, which "
            "the UI treats as 'triggering unavailable' rather than an error."
        ),
        responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        settings = PipelineSettings()
        if not settings.may_trigger(request.user):
            return Response({'detail': 'Not permitted to trigger pipelines.'}, status=403)
        try:
            # `refresh` exists so an operator who just merged a schema change can
            # see it without waiting out the TTL.
            force = request.query_params.get('refresh') == 'true'
            return Response(get_schema(settings, force=force))
        except SchemaUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)


class PipelineIndexView(generics.GenericAPIView):
    """Which tenants, namespaces and capsules exist, for the form's picklists.

    The GitLab Pages form ships this as index.json, rebuilt on each merge, and
    says so on screen because it is only as current as the last one. Here it
    comes from the dashboard's own synced state instead, which is the one thing
    OpsDash can genuinely do better -- it is minutes behind the repository
    rather than a merge behind.

    Shaped like the Pages index.json on purpose, so the picklist lookup is the
    same code on both surfaces.
    """
    serializer_class = serializers.Serializer

    @extend_schema(
        description=(
            "Existing tenants, their namespaces and their capsules, grouped by "
            "cluster. Feeds the tenant and namespace picklists in the trigger "
            "form. Decommissioned records are excluded -- they cannot be the "
            "target of a new request."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        settings = PipelineSettings()
        if not settings.may_trigger(request.user):
            return Response({'detail': 'Not permitted to trigger pipelines.'}, status=403)

        clusters = {}

        def tenant_slot(cluster_name, tenant_name):
            cluster = clusters.setdefault(cluster_name, {})
            return cluster.setdefault(tenant_name, {'namespaces': [], 'capsules': []})

        # Every active tenant, including those with nothing in them yet -- an
        # empty tenant is still a tenant you can add a namespace to.
        for name, cluster_name in (Tenant.objects
                                   .filter(is_decommissioned=False)
                                   .values_list('name', 'cluster__name')):
            if cluster_name:
                tenant_slot(cluster_name, name)

        for name, tenant_name, cluster_name in (Namespace.objects
                                                .filter(is_decommissioned=False)
                                                .values_list('name', 'tenant__name', 'cluster__name')):
            if tenant_name and cluster_name:
                tenant_slot(cluster_name, tenant_name)['namespaces'].append(name)

        for name, tenant_name, cluster_name in (Capsule.objects
                                                .filter(is_decommissioned=False)
                                                .values_list('name', 'tenant__name', 'cluster__name')):
            if tenant_name and cluster_name:
                tenant_slot(cluster_name, tenant_name)['capsules'].append(name)

        for cluster in clusters.values():
            for record in cluster.values():
                record['namespaces'].sort()
                record['capsules'].sort()

        return Response({'clusters': clusters})


class PipelineTriggerView(generics.GenericAPIView):
    """Start a pipeline.

    The only endpoint in the dashboard that causes anything to change anywhere.
    """
    serializer_class = serializers.Serializer

    @extend_schema(
        description=(
            "Start an onboarding pipeline. Body: `{\"operation\": ..., "
            "\"payload\": {...}}`.\n\n"
            "The signed-in user is recorded as TRIGGERED_BY; it is not taken "
            "from the body. `payload.requester_email` is a different thing -- "
            "the customer who raised the ITSM ticket.\n\n"
            "Field-level validation is the pipeline's own "
            "(pipeline-scripts/load-payload.sh); this endpoint checks only that "
            "the operation exists, that every key is a field that operation "
            "offers, and that the payload is scalar and within size."
        ),
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT,
                   403: OpenApiTypes.OBJECT, 502: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        settings = PipelineSettings()
        if not settings.may_trigger(request.user):
            return Response({'detail': 'Not permitted to trigger pipelines.'}, status=403)

        # Answered before anything is attempted, and as 503 rather than the 502
        # below. Both mean "not available", but 502 says the upstream failed --
        # and a 502 in the logs of an install that was simply never configured
        # sends whoever reads it to go and look at a healthy GitLab.
        if not settings.is_configured:
            return Response({'detail': settings.unavailable_reason}, status=503)

        data = request.data if isinstance(request.data, dict) else {}
        operation = data.get('operation')
        payload = data.get('payload')

        if not operation:
            return Response({'detail': 'No operation given.'}, status=400)

        try:
            result = trigger(operation, payload, _who(request.user), settings=settings)
        except TriggerRejected as exc:
            # Refused here, nothing left the process.
            return Response({'detail': str(exc)}, status=400)
        except SchemaUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        except TriggerFailed as exc:
            # 502, not 500: the dashboard did its part and the upstream refused
            # or was unreachable. The distinction matters when reading logs.
            logger.warning("Pipeline trigger failed: %s", exc)
            return Response({'detail': str(exc)}, status=502)

        return Response({
            'id': result.get('id'),
            'web_url': result.get('web_url'),
            'status': result.get('status'),
            'operation': operation,
        }, status=201)


def _who(user):
    """How the pipeline should record the person who pressed the button.

    Email when there is one, because that is what identifies someone across
    GitLab, ITSM and the repository; the username is a local artefact and means
    little outside this dashboard.
    """
    email = (getattr(user, 'email', '') or '').strip()
    username = (getattr(user, 'get_username', lambda: '')() or '').strip()
    if email and username and email != username:
        return f'{username} <{email}>'
    return email or username or 'unknown'
