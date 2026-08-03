import os
import time
import requests
import urllib3
from django.core.management.base import BaseCommand
from django.core.management import call_command

from dashboard.models import SyncAlreadyRunning

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

            time.sleep(poll_interval)