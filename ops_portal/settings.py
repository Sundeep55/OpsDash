"""
Django settings for ops_portal project.
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# =====================================================================
# OPENSHIFT PRODUCTION READINESS & ENV VARS
# =====================================================================

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-!40tdl8g59tr^*o$u)(co_qphnx4xz*aakucn*4@%y+2p^akp3')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

# OpenShift Routes inject dynamic hostnames, parse them from the environment safely
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://localhost,http://127.0.0.1').split(',')]

# Tells Django to trust the X-Forwarded-Proto header from the OpenShift/Nginx router
# so that pagination links and absolute URIs are generated as HTTPS instead of HTTP.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Database: Read the DB path from the environment so it can be stored in a PVC later
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DATABASE_PATH', BASE_DIR / 'db.sqlite3'),
        'OPTIONS': {
            # Wait for a busy writer instead of failing instantly with
            # "database is locked". WAL keeps readers unblocked (see
            # dashboard/apps.py), but writers still serialise against each other.
            'timeout': 30,
        },
    }
}

# =====================================================================
# APPLICATION CONFIGURATION
# =====================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.middleware.AutoLogoutMiddleware',
]

ROOT_URLCONF = 'ops_portal.urls'
WSGI_APPLICATION = 'ops_portal.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dashboard.context_processors.portal_config',
            ],
        },
    },
]

# =====================================================================
# SESSION & TIMEOUT SECURITY
# =====================================================================

# 1. Log users out after 30 minutes (1800 seconds) of inactivity
SESSION_COOKIE_AGE = 1800 

# 2. Automatically expire the session if the user closes their browser window
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# =====================================================================
# STATIC FILES (CSS, JavaScript, Images)
# =====================================================================

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Content-hashed filenames, so a deploy cannot leave users on a stale cached
# app.js until they hard-refresh. This previously crashed collectstatic because
# static/css/input.css -- a Tailwind SOURCE file -- begins with
# `@import "tailwindcss";`, which the manifest post-processor cannot resolve to
# a collected asset. That file now lives in assets/css/ and is not collected;
# see the comment at the top of it. base.html only ever loaded the compiled
# static/css/tailwind.css, which has no imports or url() references.
#
# Must be STORAGES, not the old STATICFILES_STORAGE: that setting was removed in
# Django 5.1 and is now ignored *silently* -- no error, no warning, `check` and
# `check --deploy` both pass, and static files quietly fall back to unhashed and
# uncompressed. Django does not merge this dict with its defaults, so the
# unused-but-required "default" entry has to be spelled out too.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}


# =====================================================================
# GLOBAL VARS, AUTH & SECURITY
# =====================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =====================================================================
# GITOPS REPOSITORY LAYOUT
# =====================================================================
# The chart names, file names and directory names the sync matches on. The
# defaults are the placeholder names used by this repository's fixtures and
# docs; the real ones differ, so set them here or via the environment.
#
# Every value is an exact match, not a pattern. See dashboard/gitops/layout.py
# for what each one selects, and docs/adding-a-section.md for adding a new
# block to the provisioner chart.
#
# Overriding via the ConfigMap means a rename in the GitOps repo does not need
# an image rebuild.
GITOPS_LAYOUT = {
    # Top-level keys inside a namespace's values file.
    'provisioner_key': os.environ.get('GITOPS_PROVISIONER_KEY', 'namespace-provisioner'),
    # A capsule's values file carries this block where a namespace carries
    # provisioner_key. It is the only thing that tells the two apart: both sit at
    # <cluster>/<tenant>/<name>/values.yaml and both are named dcsc-*.
    'capsule_key': os.environ.get('GITOPS_CAPSULE_KEY', 'tenant-provisioner'),
    'egress_key': os.environ.get('GITOPS_EGRESS_KEY', 'egress'),
    'service_mesh_key': os.environ.get('GITOPS_SERVICE_MESH_KEY', 'service-mesh'),
    'registry_config_key': os.environ.get('GITOPS_REGISTRY_CONFIG_KEY', 'registry-config'),

    # File names.
    'tenant_metadata_file': os.environ.get('GITOPS_TENANT_METADATA_FILE', 'tenant-metadata.yaml'),
    'chart_file': os.environ.get('GITOPS_CHART_FILE', 'Chart.yaml'),

    # Directory names.
    'templates_dir': os.environ.get('GITOPS_TEMPLATES_DIR', 'templates'),
    'decommissioned_tenants_dir': os.environ.get('GITOPS_DECOMMISSIONED_TENANTS_DIR', '.decommissioned_tenants'),
    'decommissioned_namespaces_dir': os.environ.get('GITOPS_DECOMMISSIONED_NAMESPACES_DIR', '.decommissioned_namespaces'),

    # Comma-separated. Files ignored outright, wherever they appear.
    'skip_filenames': tuple(
        name.strip()
        for name in os.environ.get('GITOPS_SKIP_FILENAMES', 'egressip-pool.yaml').split(',')
        if name.strip()
    ),
}

# Read from the environment because the deployment's ConfigMap has always set
# both -- they were hardcoded here, so setting them there changed nothing and
# gave no indication of why.
PORTAL_NAME = os.environ.get('PORTAL_NAME', 'Ops Control Plane')
PORTAL_TITLE = os.environ.get('PORTAL_TITLE', 'IDP Dashboard')
GIT_BROWSER_URL = os.environ.get('GIT_BROWSER_URL', '')

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =====================================================================
# REST FRAMEWORK & SWAGGER API
# =====================================================================

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication', 
        'rest_framework.authentication.BasicAuthentication',   
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated', 
    ],
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Ops Control Plane API',
    'DESCRIPTION': 'Internal Developer Portal (IDP) API for querying GitOps configurations.',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}
