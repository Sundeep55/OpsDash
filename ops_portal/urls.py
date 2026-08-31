from django.contrib import admin
from django.contrib.auth.decorators import login_required
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
    #
    # Behind login, like every other page.
    #
    # The endpoints these describe have always required authentication -- an
    # anonymous call to any of them is a 403. But the schema itself was public:
    # 47 KB naming 36 endpoints with their parameters, filters and field names,
    # readable by anyone who could reach the host. No estate data in it, so this
    # is a map of the application rather than a leak of its contents -- and an
    # internal ops tool has no reason to publish that map.
    #
    # login_required rather than a DRF permission class, so a signed-out
    # operator is redirected to the login page and comes back to the docs,
    # instead of being handed a JSON 403 by a page they expected to read.
    path('api/schema/', login_required(SpectacularAPIView.as_view()), name='schema'),
    path('api/docs/',
         login_required(SpectacularSwaggerView.as_view(url_name='schema')),
         name='swagger-ui'),
]
