from gunicorn.glogging import Logger

class CustomLogger(Logger):
    """
    Custom Gunicorn Logger that mutes specific high-frequency polling endpoints
    to prevent them from spamming the OpenShift container logs.
    """
    def access(self, resp, req, environ, request_time):
        # Mute the silent Vue.js Smart Ping endpoint. Matches both the versioned
        # path and the legacy unversioned alias.
        if req.path.endswith('/sync/status/'):
            return
            
        # Mute standard Kubernetes health checks (optional, but good practice)
        if req.path in ['/healthz', '/live', '/ready']:
            return
            
        # Log everything else normally
        super().access(resp, req, environ, request_time)

# Tell Gunicorn to use this custom logging class
logger_class = CustomLogger

# Output access logs to stdout
accesslog = '-'
