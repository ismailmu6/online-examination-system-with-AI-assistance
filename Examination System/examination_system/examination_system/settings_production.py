"""
Django settings for PRODUCTION environment.

This file contains production-specific settings that override the base settings.
It should NEVER be committed with actual secrets - use environment variables instead.

Usage:
    python manage.py runserver --settings=examination_system.settings_production
    or set DJANGO_SETTINGS_MODULE=examination_system.settings_production
"""

import os
from .settings import *

# ═══════════════════════════════════════════════════════════════════════════
# SECURITY SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# CRITICAL: Set DEBUG to False in production
DEBUG = False

# CRITICAL: SECRET_KEY must be set from environment variable
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "❌ DJANGO_SECRET_KEY environment variable must be set in production!\n"
        "Generate a secure key with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    )

# ALLOWED_HOSTS - Must be set to your actual domain(s)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    raise ValueError(
        "❌ DJANGO_ALLOWED_HOSTS environment variable must be set in production!\n"
        "Example: DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com"
    )

# ═══════════════════════════════════════════════════════════════════════════
# HTTPS/SSL SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Force HTTPS redirects
SECURE_SSL_REDIRECT = True

# Cookies should only be sent over HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HTTP Strict Transport Security (HSTS)
# Tells browsers to only use HTTPS for this site
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Don't allow browsers to guess content types
SECURE_CONTENT_TYPE_NOSNIFF = True

# Enable browser's XSS protection
SECURE_BROWSER_XSS_FILTER = True

# Prevent site from being embedded in iframes (clickjacking protection)
X_FRAME_OPTIONS = "DENY"

# Redirect HTTP Host headers to HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# For production, you should use PostgreSQL instead of SQLite
# Uncomment and configure if using PostgreSQL:
"""
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'examination_system'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # Connection pooling
        'OPTIONS': {
            'sslmode': 'require',  # For cloud databases
        }
    }
}
"""

# If staying with SQLite (NOT recommended for production):
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db_production.sqlite3",
    }
}

# ═══════════════════════════════════════════════════════════════════════════
# STATIC & MEDIA FILES
# ═══════════════════════════════════════════════════════════════════════════

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files (User uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Use WhiteNoise for serving static files in production
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

# Enable compression and caching for static files
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ═══════════════════════════════════════════════════════════════════════════
# EMAIL SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Email configuration for production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
    print("⚠️  WARNING: Email credentials not set. Email functionality will not work.")

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "production_error.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["file"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# Ensure logs directory exists
os.makedirs(BASE_DIR / "logs", exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# CACHING (Optional but recommended for production)
# ═══════════════════════════════════════════════════════════════════════════

# Using Redis for caching (requires redis-py and django-redis packages)
# Uncomment if you have Redis set up:
"""
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Use Redis for session storage
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
"""

# ═══════════════════════════════════════════════════════════════════════════
# PERFORMANCE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Template caching
TEMPLATES[0]["OPTIONS"]["loaders"] = [
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# ADMIN SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Set a more secure admin URL (change 'admin/' in urls.py to match this)
# ADMIN_URL = os.environ.get('ADMIN_URL', 'secure-admin-panel/')

# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTION CHECKLIST
# ═══════════════════════════════════════════════════════════════════════════

"""
Before deploying to production, ensure you have:

✅ Environment Variables Set:
   - DJANGO_SECRET_KEY (use a strong, random key)
   - DJANGO_ALLOWED_HOSTS (comma-separated list of domains)
   - EMAIL_HOST_USER
   - EMAIL_HOST_PASSWORD
   - DB_PASSWORD (if using PostgreSQL)

✅ Security:
   - SSL certificate installed
   - Firewall configured
   - Regular backups scheduled
   - Monitoring and alerting set up

✅ Performance:
   - Static files collected (python manage.py collectstatic)
   - Database migrations applied (python manage.py migrate)
   - Consider using a CDN for static files
   - Consider using Redis for caching

✅ Testing:
   - Run: python manage.py check --deploy
   - Load test your application
   - Test all critical user flows

✅ Monitoring:
   - Set up error tracking (e.g., Sentry)
   - Set up uptime monitoring
   - Set up performance monitoring

Commands to run before deployment:
    python manage.py check --deploy
    python manage.py collectstatic --noinput
    python manage.py migrate
"""

# ═══════════════════════════════════════════════════════════════════════════
# END OF PRODUCTION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

print("✅ Production settings loaded successfully")
print(f"   Allowed hosts: {ALLOWED_HOSTS}")
print(f"   Debug mode: {DEBUG}")
print(f"   Database: {DATABASES['default']['ENGINE']}")

