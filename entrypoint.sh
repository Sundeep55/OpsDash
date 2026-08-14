#!/bin/bash
set -e

# Determine container mode (Web Server vs Polling Sidecar)
if [ "$1" = "sidecar" ]; then
    echo "Starting GitLab Polling Daemon..."
    # Sleep to ensure the main web container applies DB migrations first
    sleep 10 
    exec python manage.py poll_gitlab_pipelines
else
    echo "Applying database migrations..."
    # Migrations are committed to the repo and baked into the image. Never generate
    # them at runtime: that makes the schema depend on pod start order and silently
    # diverges from the DB already on the PVC.
    python manage.py migrate --noinput

    if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
        echo "Ensuring Admin Superuser exists..."
        python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_portal.settings')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
password = os.environ['DJANGO_SUPERUSER_PASSWORD']
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@xxx.com'), password=password)
    print('Superuser created successfully.')
else:
    print('Superuser already exists. Skipping creation.')
"
    fi

    echo "Starting Gunicorn Web Server with custom access logging..."
    exec gunicorn ops_portal.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 2 --timeout 60 -c gunicorn.conf.py
fi