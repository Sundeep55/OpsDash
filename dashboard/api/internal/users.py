"""Users aggregated across namespaces and capsules, and one user's access map.

A person's access is not only to namespaces. A capsule carries the same
project_owner_config / project_user_config blocks, and someone who owns three
capsules and no namespaces has real access to the estate -- they can create
namespaces inside those capsules. Counting only namespaces showed them as having
none, which is the opposite of the truth.
"""
from django.db.models import Case, Count, F, IntegerField, Q, When
from django.db.models.functions import Lower
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.pagination import StandardResultsSetPagination
from dashboard.models import UserAccess
from dashboard.serializers import UserListSerializer


def _cluster_filter(cluster):
    """Narrow to one cluster across both kinds of access.

    A row points at a namespace or a capsule, never both, so the cluster lives
    down one of two paths.
    """
    if not cluster or cluster == 'All':
        return Q()
    return Q(namespace__cluster__name=cluster) | Q(capsule__cluster__name=cluster)


class UserListView(generics.ListAPIView):
    serializer_class = UserListSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter]
    search_fields = ['email']

    def get_queryset(self):
        qs = UserAccess.objects.filter(_cluster_filter(self.request.query_params.get('cluster')))

        return (
            qs.annotate(lower_email=Lower('email'))
              .values('lower_email')
              .annotate(
                  # Kept as the namespace count it has always been, so nothing
                  # that reads access_count silently changes meaning.
                  access_count=Count('namespace', distinct=True),
                  capsule_count=Count('capsule', distinct=True),
                  email=F('lower_email'),
              )
              .order_by('lower_email')
        )


class UserDetailView(APIView):
    @extend_schema(
        description=(
            "One person's access across the estate. `data` carries both "
            "namespace and capsule memberships; each entry has a `kind` of "
            "`namespace` or `capsule`."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, email):
        cluster = request.query_params.get('cluster')

        qs = (UserAccess.objects
              .annotate(lower_email=Lower('email'))
              .filter(lower_email=email.lower())
              .filter(_cluster_filter(cluster))
              .select_related(
                  'namespace', 'namespace__tenant', 'namespace__cluster',
                  'capsule', 'capsule__tenant', 'capsule__cluster',
              ))

        access_map = {}
        for access in qs:
            target = access.namespace or access.capsule
            if target is None or target.tenant is None or target.cluster is None:
                # A row whose target lost its tenant or cluster mid-sync. Skip it
                # rather than render a membership with blanks in it.
                continue

            kind = 'namespace' if access.namespace_id else 'capsule'
            key = f'{kind}-{target.cluster.name}-{target.tenant.name}-{target.name}'
            if key not in access_map:
                access_map[key] = {
                    'kind': kind,
                    'name': target.name,
                    # Kept so anything still reading `namespace` keeps working;
                    # for a capsule it is the capsule's name.
                    'namespace': target.name,
                    'tenant': target.tenant.name,
                    'cluster': target.cluster.name,
                    'lifecycle': target.lifecycle,
                    'is_decommissioned': target.is_decommissioned,
                    'roles': set(),
                }
            access_map[key]['roles'].add(access.role)

        merged = []
        for entry in access_map.values():
            entry['role'] = ' & '.join(sorted(entry.pop('roles')))
            merged.append(entry)

        # Namespaces first, then capsules, each alphabetical -- so the list has a
        # stable shape rather than interleaving two kinds of thing by name.
        merged.sort(key=lambda e: (e['kind'] != 'namespace', e['name']))

        return Response({
            'email': email,
            'data': merged,
            'counts': {
                'namespaces': sum(1 for e in merged if e['kind'] == 'namespace'),
                'capsules': sum(1 for e in merged if e['kind'] == 'capsule'),
            },
        })
