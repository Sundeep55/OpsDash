import os
import time
import requests
import urllib3
from django.core.management.base import BaseCommand
from django.core.management import call_command

from dashboard.models import SyncAlreadyRunning

# Touched at the end of every poll iteration so the container's liveness probe
# can tell "looping" from "wedged". The loop swallows every exception by design
# -- a network blip must not kill the daemon -- which also means a permanently
# stuck iteration would otherwise look healthy forever, because the process is
# still running and nothing crashes.
#
# /tmp rather than the PVC: it is per-container, writable under OpenShift's
# random UID, and must not survive a restart.
HEARTBEAT_PATH = os.environ.get('SIDECAR_HEARTBEAT_PATH', '/tmp/sidecar-heartbeat')


def touch_heartbeat(path=HEARTBEAT_PATH):
    """Record that the poll loop completed an iteration.

    Best-effort: a failure to write must never take down a daemon that is
    otherwise doing its job. A stale file trips the probe soon enough anyway.
    """
    try:
        with open(path, 'w') as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass


class Command(BaseCommand):
    help = 'Runs as a daemon watching GitLab for successful pipelines to trigger a database sync'

    def handle(self, *args, **options):
        gitlab_url = os.environ.get('GITLAB_URL')
        token = os.environ.get('GITLAB_TOKEN')
        project_id = os.environ.get('GITLAB_PROJECT_ID')
        ssl_verify = os.environ.get('GITLAB_SSL_VERIFY', 'true').lower() == 'true'
        poll_interval = int(os.environ.get('POLL_INTERVAL_SECONDS', 60))

        if not all([gitlab_url, token, project_id]):
            self.stdout.write(self.style.ERROR("Missing GitLab credentials. Exiting polling daemon."))
            return

        if not ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # --- FIX: Removed the ?ref={branch} filter. 
        # This now triggers on ANY successful pipeline (including MR pipelines).
        # Since sync_gitops always downloads the main branch anyway, this is perfectly safe!
        api_url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{project_id}/pipelines?status=success&per_page=1"
        headers = {"PRIVATE-TOKEN": token}

        last_pipeline_id = None
        self.stdout.write(self.style.SUCCESS(f"Starting GitLab Polling Daemon (Interval: {poll_interval}s)..."))

        # Before the baseline sync, which at full scale takes long enough that
        # the probe would otherwise see no heartbeat at all on a cold start.
        touch_heartbeat()

        # Always run a baseline sync when the container first starts
        self.stdout.write(self.style.NOTICE("Running initial baseline sync on startup..."))
        try:
            call_command('sync_gitops')
        except SyncAlreadyRunning:
            self.stdout.write(self.style.NOTICE("Baseline sync skipped: another sync holds the lock."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Initial sync failed: {e}"))

        while True:
            try:
                response = requests.get(api_url, headers=headers, verify=ssl_verify, timeout=10)
                response.raise_for_status()
                pipelines = response.json()

                if pipelines:
                    latest_id = pipelines[0]['id']
                    
                    if last_pipeline_id is None:
                        last_pipeline_id = latest_id
                    elif latest_id != last_pipeline_id:
                        self.stdout.write(self.style.SUCCESS(f"New successful pipeline detected (ID: {latest_id}). Triggering DB sync..."))
                        try:
                            call_command('sync_gitops')
                            last_pipeline_id = latest_id
                        except SyncAlreadyRunning:
                            # Deliberately do NOT advance last_pipeline_id: this
                            # pipeline is still unprocessed, so retry next tick
                            # once the in-flight sync releases the lock.
                            self.stdout.write(self.style.NOTICE("Sync already running; will retry on the next poll."))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Sync failed during polling: {e}"))
                            
            except Exception as e:
                # Catch network blips without crashing the daemon
                self.stdout.write(self.style.WARNING(f"Failed to poll GitLab API: {e}"))

            # Outside the try: reaching here means the iteration finished, even
            # if GitLab was unreachable. Retrying is the daemon working, not
            # failing -- an unreachable GitLab should not restart the container.
            touch_heartbeat()
            time.sleep(poll_interval)