"""GitLab archive download, extraction and temp-directory lifecycle."""
import logging
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager

import requests
import urllib3

logger = logging.getLogger(__name__)

# The download must never block forever: a hung connection would hold the sync
# lock until it goes stale, and the threaded HTTP caller discards the traceback.
# (connect timeout, read timeout) -- read applies per chunk, not to the whole body.
GITLAB_TIMEOUT = (10, 60)


class GitLabSettings:
    """GitLab connection details, read from the environment."""

    def __init__(self, env=None):
        env = env if env is not None else os.environ
        self.url = env.get('GITLAB_URL')
        self.token = env.get('GITLAB_TOKEN')
        self.project_id = env.get('GITLAB_PROJECT_ID')
        self.branch = env.get('GITLAB_BRANCH', 'main')
        self.ssl_verify = env.get('GITLAB_SSL_VERIFY', 'true').lower() == 'true'

    @property
    def is_configured(self):
        return bool(self.url and self.token and self.project_id)


def _safe_extract(zip_ref, dest):
    """Extract without letting archive members escape `dest`.

    zipfile does not validate member paths, so an archive containing '../'
    entries can write anywhere the process can reach. The repo is our own, but
    this is a cheap guard on a code path that runs unattended as a daemon.
    """
    dest_root = os.path.realpath(dest)
    for member in zip_ref.infolist():
        target = os.path.realpath(os.path.join(dest, member.filename))
        if target != dest_root and not target.startswith(dest_root + os.sep):
            raise ValueError(f"Refusing to extract outside the target directory: {member.filename}")
    zip_ref.extractall(dest)


def download_archive(settings, log=None):
    """Download and extract the repository archive.

    Returns (repo_root, temp_dir): the directory to walk, and the directory to
    delete afterwards. GitLab wraps the tree in a single commit-named folder, so
    those two differ.
    """
    if log:
        log(f"Connecting to GitLab: {settings.url} (Project: {settings.project_id}, "
            f"Branch: {settings.branch}, SSL Verify: {settings.ssl_verify})...")

    if not settings.ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    api_url = (f"{settings.url.rstrip('/')}/api/v4/projects/{settings.project_id}"
               f"/repository/archive.zip?sha={settings.branch}")

    response = requests.get(
        api_url,
        headers={"PRIVATE-TOKEN": settings.token},
        stream=True,
        verify=settings.ssl_verify,
        timeout=GITLAB_TIMEOUT,
    )
    response.raise_for_status()

    temp_dir = tempfile.mkdtemp(prefix="gitops_sync_")
    zip_path = os.path.join(temp_dir, 'repo.zip')

    with open(zip_path, 'wb') as fh:
        for chunk in response.iter_content(chunk_size=8192):
            fh.write(chunk)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        _safe_extract(zip_ref, temp_dir)

    os.remove(zip_path)

    extracted = [
        os.path.join(temp_dir, entry)
        for entry in os.listdir(temp_dir)
        if os.path.isdir(os.path.join(temp_dir, entry))
    ]
    return (extracted[0] if extracted else temp_dir), temp_dir


@contextmanager
def repository(local_path, settings=None, log=None):
    """Yield a directory to walk, cleaning up any temp files afterwards.

    Falls back to `local_path` when GitLab is not configured or the download
    fails, preserving the original behaviour: a failed fetch does not abort the
    run, it drops through to whatever is on disk. The caller checks the path
    exists before walking it.
    """
    settings = settings if settings is not None else GitLabSettings()
    temp_dir = None
    repo_path = local_path

    try:
        if settings.is_configured:
            try:
                repo_path, temp_dir = download_archive(settings, log=log)
                if log:
                    log("Successfully fetched and extracted repository from GitLab.")
            except Exception as exc:
                # exc_info here: unlike a malformed file this is unexpected, rare,
                # and the traceback distinguishes a timeout from an auth failure
                # from a bad archive.
                logger.warning("GitLab fetch failed, falling back to %s", local_path, exc_info=True)
                if log:
                    log(f"GitLab sync failed: {exc}")
                    log(f"Falling back to local repository path: {local_path}")
        elif log:
            log(f"GitLab environment variables missing. Using local repository path: {local_path}")

        yield repo_path
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            if log:
                log("Cleaned up temporary GitLab repository files.")
