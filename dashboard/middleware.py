import time
from django.contrib.auth import logout
from django.conf import settings

# How stale the stored activity timestamp may get before we rewrite it.
# Assigning to request.session marks it dirty, which writes a row to the DB on
# every single request -- and those writes serialise against sync_gitops. At 60s
# the write volume drops by orders of magnitude; the cost is that the idle
# timeout can fire up to this many seconds early, which is noise against a
# 30-minute window.
ACTIVITY_REFRESH_INTERVAL = 60

# The UI polls this on a timer. Refreshing the idle clock from it would keep a
# session alive forever on an unattended tab. Both the versioned path and the
# legacy alias resolve to the same view, so both must be listed.
SYNC_STATUS_PATHS = ('/api/v2/sync/status/', '/api/sync/status/')


class AutoLogoutMiddleware:
    """Log out sessions idle for longer than SESSION_COOKIE_AGE.

    Plain callable rather than MiddlewareMixin: the mixin exists only to adapt
    pre-1.10 middleware and brings no benefit here.

    Note this does not affect API clients authenticating with Basic auth. It
    runs before DRF authentication, so for a request with no session cookie
    request.user is AnonymousUser and it returns immediately.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.check_idle(request)
        return self.get_response(request)

    def check_idle(self, request):
        if not request.user.is_authenticated:
            return

        # Skip session reset for background UI polling to prevent infinite sessions
        if request.path.startswith(SYNC_STATUS_PATHS):
            return

        current_time = time.time()
        last_activity = request.session.get('last_activity')
        timeout_seconds = getattr(settings, 'SESSION_COOKIE_AGE', 1800)

        if last_activity is None:
            # First request of the session: start the clock, never log out.
            request.session['last_activity'] = current_time
            return

        idle_seconds = current_time - last_activity

        if idle_seconds > timeout_seconds:
            # The user was inactive for too long, log them out securely
            logout(request)
            return

        # The user clicked around or loaded a page, reset the inactivity timer --
        # but only once the stored value has actually gone stale, so a burst of
        # API calls does not become a burst of session writes.
        if idle_seconds > ACTIVITY_REFRESH_INTERVAL:
            request.session['last_activity'] = current_time
