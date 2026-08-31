"""The route-exception list, for the SPA.

The expiry banner needs this and is a browser, so it authenticates with the
session like every other internal endpoint. The product copy of the same
endpoint is token-only; see dashboard/api/product/auth.py.

Subclassed rather than reimplemented. The banner and any notifier reading the
product API must agree about what is expiring -- that was the reason the banner
was pointed at the product endpoint in the first place, and duplicating the
queryset here to change one attribute would have thrown it away. The filtering,
the ordering and the expiry window all still live in exactly one place; this
class changes who is allowed to ask.
"""
from rest_framework.authentication import SessionAuthentication

from dashboard.api.product.security import SecurityRouteExceptionApiView


class InternalRouteExceptionApiView(SecurityRouteExceptionApiView):
    authentication_classes = [SessionAuthentication]
