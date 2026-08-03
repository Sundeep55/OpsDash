"""Everything under /api/v2/, both audiences.

Internal routes are listed first so a product path can never shadow one the SPA
depends on.
"""
from django.urls import include, path

urlpatterns = [
    path('', include('dashboard.api.internal.urls')),
    path('', include('dashboard.api.product.urls')),
]
