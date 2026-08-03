from django.conf import settings

def portal_config(request):
    """
    Exposes global settings to all HTML templates automatically.
    """
    return {
        'portal_name': getattr(settings, 'PORTAL_NAME', 'Ops Control Plane'),
        'portal_title': getattr(settings, 'PORTAL_TITLE', 'Ops Portal Dashboard'),
        'git_browser_url': getattr(settings, 'GIT_BROWSER_URL', ''),
        # Handed to the Vue app via json_script rather than as globals.
        'portal_config': {
            'gitBrowserUrl': getattr(settings, 'GIT_BROWSER_URL', ''),
        },
        # Chooses the Vue build in base.html. Django's own `debug` context
        # processor only populates when the client IP is in INTERNAL_IPS, which
        # is never true behind the OpenShift router, so it cannot be used here.
        'debug': settings.DEBUG,
    }