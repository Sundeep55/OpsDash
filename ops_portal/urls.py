from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from dashboard import health

urlpatterns = [
    # --- KUBELET PROBES ---
    # Unauthenticated and mounted at the root, before anything else. No trailing
    # slash, so APPEND_SLASH cannot turn a probe into a 301 that the kubelet
    # counts as a failure -- and so gunicorn.conf.py keeps muting them.
    path('healthz', health.liveness, name='healthz'),
    path('readyz', health.readiness, name='readyz'),

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
