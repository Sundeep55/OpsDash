from django.conf import settings

def portal_config(request):
    """
    Exposes global settings to all HTML templates automatically.
    """
    return {
        'portal_name': getattr(settings, 'PORTAL_NAME', 'Ops Control Plane'),
        'portal_title': getattr(settings, 'PORTAL_TITLE', 'Ops Portal Dashboard'),
        'git_browser_url': getattr(settings, 'GIT_BROWSER_URL', ''),
    }