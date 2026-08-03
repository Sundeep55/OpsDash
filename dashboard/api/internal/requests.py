"""Request tickets, grouped by ticket id."""
import collections

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import Tenant


class RequestTicketListView(APIView):
    @extend_schema(responses={200: OpenApiTypes.ANY})
    def get(self, request):
        search = request.query_params.get('search', '').lower()
        
        t_qs = Tenant.objects.exclude(request_ticket__isnull=True)
        if search: t_qs = t_qs.filter(request_ticket__icontains=search)
        
        res = collections.defaultdict(list)
        for t in t_qs:
            res[t.request_ticket].append({"type": "Tenant", "name": t.name})
            
        return Response([{"id": k, "data": v} for k, v in res.items()])
