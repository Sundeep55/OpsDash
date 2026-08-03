from django.core.management.base import BaseCommand

from dashboard.gitops import sync_repository
from dashboard.gitops.status import sync_lock


class Command(BaseCommand):
    help = 'Fetches GitOps YAML files from GitLab (or local fallback) and safely upserts them into the Database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo-path',
            type=str,
            default='/projects/tools/customer-instances',
            help='Fallback local path to the GitOps cluster/tenant folders if GitLab is not configured',
        )
        parser.add_argument(
            '--lock-held',
            action='store_true',
            help=(
                'Internal. Declares that the caller already claimed the sync lock via '
                'SystemSyncStatus.try_acquire(). Used by TriggerSyncView, which must take '
                'the lock synchronously so it can return an accurate 409 before spawning '
                'its worker thread. Do not pass this by hand.'
            ),
        )

    def handle(self, *args, **options):
        with sync_lock(already_held=options['lock_held']) as report:
            outcome, error = sync_repository(
                options['repo_path'], report=report, log=self.stdout.write
            )

            if error:
                report.finish(error)
                return

            count, pruned = outcome
            report.finish("Ready", completed=True)
            self.stdout.write(self.style.SUCCESS(
                f"✅ GitOps Sync Complete! Safely updated database with "
                f"configurations from {count} namespaces."
            ))
