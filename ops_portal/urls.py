from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from dashboard.api.internal.urls import legacy_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- AUTHENTICATION URLS ---
    path('accounts/', include('django.contrib.auth.urls')),

    path('', include('dashboard.urls')),

    # --- API v2: internal (Vue SPA) + product (external consumers) ---
    # See dashboard/api/ for the split; each half owns its own urls.py.
    path('api/v2/', include('dashboard.api.urls')),

    # --- SWAGGER API DOCS ---
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# Unversioned /api/sync/ aliases, still called by app.js.
urlpatterns += legacy_urlpatterns
