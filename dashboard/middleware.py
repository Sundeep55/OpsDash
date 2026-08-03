import time
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import logout
from django.conf import settings

# How stale the stored activity timestamp may get before we rewrite it.
# Assigning to request.session marks it dirty, which writes a row to the DB on
# every single request -- and those writes serialise against sync_gitops. At 60s
# the write volume drops by orders of magnitude; the cost is that the idle
# timeout can fire up to this many seconds early, which is noise against a
# 30-minute window.
ACTIVITY_REFRESH_INTERVAL = 60


class AutoLogoutMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            return

        # Skip session reset for background UI polling to prevent infinite sessions
        if request.path.startswith('/api/sync/status/'):
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
