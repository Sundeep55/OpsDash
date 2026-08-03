"""Users aggregated across namespaces, and a single user's access map."""
from django.db.models import Count, F
from django.db.models.functions import Lower
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.pagination import StandardResultsSetPagination
from dashboard.models import UserAccess
from dashboard.serializers import UserListSerializer


class UserListView(generics.ListAPIView):
    serializer_class = UserListSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter]
    search_fields = ['email']

    def get_queryset(self):
        qs = UserAccess.objects.all()
        cluster = self.request.query_params.get('cluster')
        if cluster and cluster != 'All':
            qs = qs.filter(namespace__cluster__name=cluster)
            
        return qs.annotate(lower_email=Lower('email')) \
                 .values('lower_email') \
                 .annotate(access_count=Count('namespace', distinct=True), email=F('lower_email')) \
                 .order_by('lower_email')


class UserDetailView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, email):
        cluster = request.query_params.get('cluster')
        
        qs = UserAccess.objects.annotate(lower_email=Lower('email')) \
                               .filter(lower_email=email.lower()) \
                               .select_related('namespace', 'namespace__tenant', 'namespace__cluster')
        
        if cluster and cluster != 'All':
            qs = qs.filter(namespace__cluster__name=cluster)
            
        access_map = {}
        for access in qs:
            key = f"{access.namespace.cluster.name}-{access.namespace.tenant.name}-{access.namespace.name}"
            if key not in access_map:
                access_map[key] = {
                    "namespace": access.namespace.name,
                    "tenant": access.namespace.tenant.name,
                    "cluster": access.namespace.cluster.name,
                    "roles": set()
                }
            access_map[key]["roles"].add(access.role)
            
        merged_data = []
        for v in access_map.values():
            v['role'] = ' & '.join(sorted(list(v['roles'])))
            del v['roles']
            merged_data.append(v)
            
        merged_data.sort(key=lambda x: x['namespace'])
        return Response({"email": email, "data": merged_data})
