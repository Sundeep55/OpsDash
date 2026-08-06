from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    # Portal name, title and git browser URL all come from the
    # dashboard.context_processors.portal_config context processor, which is
    # registered in settings and runs for every template.
    #
    # This view used to build its own context from settings.OPS_PORTAL_NAME and
    # OPS_PORTAL_TITLE -- names that do not exist (the settings are PORTAL_NAME
    # and PORTAL_TITLE), so both always fell through to their hardcoded
    # fallbacks and neither was ever read by a template.
    return render(request, 'dashboard/index.html')
