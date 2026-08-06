# =============================================================================
# Stage 1: build the virtualenv.
#
# Split out so pip, setuptools, wheel and any transient build dependencies stay
# out of the runtime image. Only the finished site-packages tree is carried
# forward, which both shrinks the image and removes tooling that shows up in CVE
# scans without ever being executed in production.
# =============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Patch the build stage too: a wheel compiled here against a vulnerable system
# library would carry the problem into the runtime image.
RUN apt-get update && apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*

# --- CVE FIX: patch the build tooling before it is used ---
RUN pip install --upgrade pip setuptools "wheel>=0.46.2"

# Self-contained venv, copied wholesale into the runtime stage. Same path in
# both stages, because a venv records absolute paths.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# Drop bytecode and test suites that shipped inside the wheels. Nothing imports
# them, and they are a meaningful share of the tree.
RUN find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + && \
    find /opt/venv -type d -name 'tests' -prune -exec rm -rf {} + && \
    find /opt/venv -type f -name '*.pyc' -delete


# =============================================================================
# Stage 2: runtime.
# =============================================================================
FROM python:3.12-slim

# Python 3.12: the newest release Django 4.2 supports (3.8-3.12), and still
# receiving security patches. The development boxes run 3.9, which is itself
# end-of-life -- so the *code* is kept importable on 3.9 (enforced by
# tools/check_py39_compat.py) while the image runs a supported interpreter.
#
# If the approved base-image list does not carry 3.12, 3.11 or 3.10 work
# equally well; do not drop to 3.9, which stopped receiving security fixes in
# October 2025.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

USER root

# --- CVE FIX: apply OS-level security patches (OpenSSL, Perl, Ncurses, etc.) ---
# Kept in the runtime stage as well: this is what a scanner reads, and the base
# image is only rebuilt when the tag moves.
RUN apt-get update && apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Explicitly copy only required application files. See .dockerignore -- without
# it these would also carry the host's __pycache__ into the image.
COPY manage.py /app/
COPY ops_portal/ /app/ops_portal/
COPY dashboard/ /app/dashboard/
COPY static/ /app/static/
COPY entrypoint.sh /app/
COPY gunicorn.conf.py /app/
# Probe script for the sidecar's exec liveness check.
COPY bin/ /app/bin/
# Just the compatibility gate, not all of tools/ -- the rest is developer
# tooling the runtime never reads.
COPY tools/check_py39_compat.py /app/tools/
COPY tools/check_templates.py /app/tools/

# OpenShift Security Fix:
# OpenShift runs containers with random UIDs, but they are always part of Group 0
# (root). We must make the application directory writable by Group 0.
RUN mkdir -p /app/staticfiles && \
    chgrp -R 0 /app && \
    chmod -R g=u /app

# Switch to the standard non-root user for execution
USER 1001

# Fail the build on syntax the development boxes' Python 3.9 cannot run. This
# image runs 3.12, so such code would build here and crash there -- which is
# exactly what happened with a PEP 604 union in a dataclass annotation.
RUN python3 tools/check_py39_compat.py

# Fail the build on a Vue component the HTML parser would relocate. Such a
# template serves fine and renders blank under the production Vue build, so the
# symptom appears only after DEBUG=False -- usually the first real deploy.
RUN python3 tools/check_templates.py

# Fail the build if a template references a CSS class the stylesheet lacks.
# Without this the class silently resolves to nothing and the element renders
# unstyled at runtime -- see dashboard/management/commands/build_css.py.
RUN python manage.py build_css --check

# Bake the static files directly into the image (Now runs safely as non-root!)
RUN python manage.py collectstatic --noinput

# Expose the port Gunicorn will listen on
EXPOSE 8000

# Run the initialization script by explicitly calling bash
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
