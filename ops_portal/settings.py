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

# Using CompressedStaticFilesStorage avoids the CSS import parsing crash 
# caused by the missing local tailwind file, while still compressing assets.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'


# =====================================================================
# GLOBAL VARS, AUTH & SECURITY
# =====================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

PORTAL_NAME = "Ops Control Plane"
PORTAL_TITLE = "Airbus IDP Dashboard"
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
