from django.shortcuts import render
from django.conf import settings
from django.contrib.auth.decorators import login_required

@login_required
def index(request):
    # Pass the global settings to the template, providing fallbacks just in case
    context = {
        'app_name': getattr(settings, 'OPS_PORTAL_NAME', 'Ops Control Plane'),
        'page_title': getattr(settings, 'OPS_PORTAL_TITLE', 'Ops Portal'),
    }
    return render(request, 'dashboard/index.html', context)
