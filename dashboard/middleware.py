import time
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import logout
from django.conf import settings

class AutoLogoutMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            return

        # Skip session reset for background UI polling to prevent infinite sessions
        if request.path.startswith('/api/sync/status/'):
            return

        current_time = time.time()
        last_activity = request.session.get('last_activity', current_time)
        
        # Default to 30 minutes (1800 seconds) if not explicitly set in settings.py
        timeout_seconds = getattr(settings, 'SESSION_COOKIE_AGE', 1800)

        if (current_time - last_activity) > timeout_seconds:
            # The user was inactive for too long, log them out securely
            logout(request)
        else:
            # The user clicked around or loaded a page, reset the inactivity timer
            request.session['last_activity'] = current_time
