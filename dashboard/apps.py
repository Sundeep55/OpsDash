import logging

from django.apps import AppConfig
from django.db.backends.signals import connection_created

logger = logging.getLogger(__name__)

_wal_checked = False


def configure_sqlite(sender, connection, **kwargs):
    """Put SQLite in WAL mode on every new connection.

    In the default rollback-journal mode a writer blocks all readers, so a long
    sync_gitops run stalls every dashboard request behind it. WAL lets readers
    continue against the last committed snapshot while the sync writes.

    journal_mode is persisted in the database file header, so this only really
    takes effect once -- but a fresh DB (the file is disposable and rebuilt from
    Git) needs it applied again, and setting it per-connection is cheap.
    """
    global _wal_checked
    if connection.vendor != 'sqlite':
        return

    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        mode = (cursor.fetchone() or [''])[0]
        # NORMAL is the standard companion to WAL: fsync at checkpoints rather
        # than every commit. On power loss it can lose the most recent
        # transactions but cannot corrupt the file -- and this DB is rebuildable
        # from Git at any time, so durability is not worth the write cost.
        cursor.execute('PRAGMA synchronous=NORMAL;')

    if not _wal_checked:
        _wal_checked = True
        if str(mode).lower() != 'wal':
            # WAL cannot engage on some network filesystems. Fail loudly rather
            # than silently degrading back to reader-blocking behaviour.
            logger.warning(
                "SQLite refused WAL mode (journal_mode=%r). Readers will block "
                "during sync. Is the database on a network filesystem?", mode
            )


class DashboardConfig(AppConfig):
    name = 'dashboard'

    def ready(self):
        connection_created.connect(configure_sqlite)
