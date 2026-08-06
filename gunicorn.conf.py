from gunicorn.glogging import Logger

class CustomLogger(Logger):
    """
    Custom Gunicorn Logger that mutes specific high-frequency polling endpoints
    to prevent them from spamming the OpenShift container logs.
    """
    def access(self, resp, req, environ, request_time):
        # Mute the sync-status endpoint the UI polls on a timer.
        if req.path.endswith('/sync/status/'):
            return
            
        # Mute the kubelet probes. These fire every few seconds for the life
        # of the pod and would otherwise be the bulk of the access log.
        if req.path in ('/healthz', '/readyz'):
            return
            
        # Log everything else normally
        super().access(resp, req, environ, request_time)

# Tell Gunicorn to use this custom logging class
logger_class = CustomLogger

# Output access logs to stdout
accesslog = '-'
