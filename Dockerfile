# Python 3.13: 3.9 reached end of life in October 2025 and stopped receiving
# security patches. 3.13 is within Django 5.2 LTS's supported range (3.10-3.13).
FROM python:3.13-slim

# Prevent Python from writing pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Switch to root to ensure we can create directories and set permissions
USER root

# --- CVE FIX: Apply OS-level security patches (OpenSSL, Perl, Ncurses, etc.) ---
RUN apt-get update && apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- CVE FIX: Upgrade core Python build tools to patch 'wheel' vulnerabilities ---
RUN pip install --no-cache-dir --upgrade pip setuptools "wheel>=0.46.2"

WORKDIR /app

# Install dependencies 
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly copy only required application files
COPY manage.py /app/
COPY ops_portal/ /app/ops_portal/
COPY dashboard/ /app/dashboard/
COPY static/ /app/static/
COPY entrypoint.sh /app/
COPY gunicorn.conf.py /app/

# OpenShift Security Fix: 
# OpenShift runs containers with random UIDs, but they are always part of Group 0 (root).
# We must make the application directory writable by Group 0.
RUN mkdir -p /app/staticfiles && \
    chgrp -R 0 /app && \
    chmod -R g=u /app

# Switch to the standard non-root user for execution
USER 1001

# Bake the static files directly into the image (Now runs safely as non-root!)
RUN python manage.py collectstatic --noinput

# Expose the port Gunicorn will listen on
EXPOSE 8000

# Run the initialization script by explicitly calling bash
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]