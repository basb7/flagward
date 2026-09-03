"""
Django settings for flagward project.
"""
import os
from datetime import timedelta
from pathlib import Path


def env_flag(name, default):
    """Read a boolean setting from the environment."""
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default):
    """Read a comma-separated setting from the environment."""
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


def env_base_url(name, default):
    """
    Read a base-URL setting from the environment, stripped of surrounding
    whitespace and any trailing slash(es) -- so code that joins a path onto
    it (e.g. `f"{FRONTEND_BASE_URL}/reset-password/{token}"`) never produces
    a doubled slash just because an operator's `.env` happened to end the
    value with one. No other validation happens here: same permissive stance
    this file already takes with `EMAIL_HOST` and `CORS_ALLOWED_ORIGINS`,
    neither of which is checked for being a well-formed URL either.
    """
    return os.getenv(name, default).strip().rstrip('/')


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
# The fallback is for local development only; always set SECRET_KEY in production.
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_flag('DEBUG', True)

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]')

# CSRF trusted origins for frontend
CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:3000,http://localhost:5173',
)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # Local apps
    'core',
    'core_flags',
    'sdk_api',
    'analytics',
    'authentication',
    'tenancy',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS - must be before CommonMiddleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database - PostgreSQL if available, SQLite as fallback for development
if os.getenv('DB_NAME') or os.getenv('USE_POSTGRES'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'flagward'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Cache - Redis if available, LocMemCache as fallback
if os.getenv('REDIS_URL'):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': os.getenv('REDIS_URL'),
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# Redis Streams (optional)
REDIS_STREAMS_URL = os.getenv('REDIS_STREAMS_URL')

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# With DEBUG on, django.contrib.staticfiles serves these through runserver. With
# DEBUG off it stops, so WhiteNoise takes over and serves the files collected
# into STATIC_ROOT at image build time. Adding it in development would only warn
# about the STATIC_ROOT that collectstatic has not created yet.
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

if not DEBUG:
    MIDDLEWARE.insert(
        MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
        'whitenoise.middleware.WhiteNoiseMiddleware',
    )
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            # Compresses and hashes filenames for long-lived cache headers.
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    # This API is authenticated by the JWT cookie or an SDK API key. The Django
    # admin has its own session middleware and never reaches DRF, so
    # SessionAuthentication authenticated nobody here -- it only intercepted
    # requests from anyone holding an admin session on the same origin and
    # started demanding a CSRF token the dashboard does not send.
    #
    # Order also matters beyond precedence: DRF reads the WWW-Authenticate
    # header from the first class listed and downgrades 401 to 403 when it has
    # none, which would leave the client unable to tell an expired token from a
    # permission denial, and so unable to know a refresh is worth attempting.
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'authentication.jwt_auth.JWTAuthenticationCookie',
        'sdk_api.authentication.SDKAuthentication',
    ],
    # Fail-closed principal check (spec/access-control: Non-User Principal
    # Fails Closed): a dashboard route requires a Django `User`, never an
    # api-key principal. Placed globally so a viewset added later is
    # protected without its author doing anything -- verified safe for the
    # SDK surface because every SDK endpoint declares its own
    # `IsSDKAuthenticated` permission class, and the SSE stream is a plain
    # Django view that never reaches DRF.
    'DEFAULT_PERMISSION_CLASSES': [
        'tenancy.permissions.IsDashboardUser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Scoped throttle for the password-reset request endpoint (see
    # authentication.throttling.PasswordResetRequestThrottle): keyed on the
    # *target* email address rather than the caller's IP, so it limits how
    # often one mailbox can be flooded with reset emails regardless of how
    # many different IPs the requests come from. It does not limit an
    # attacker who spreads requests across many different target addresses
    # from one IP, and it does not equalise response timing between a known
    # and an unknown address.
    'DEFAULT_THROTTLE_RATES': {
        'password_reset_request': '3/hour',
    },
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    # Cookie settings for httpOnly
    'AUTH_COOKIE': 'access_token',
    'AUTH_COOKIE_REFRESH': 'refresh_token',
    # Sent over HTTPS only whenever DEBUG is off, so production never
    # downgrades the auth cookies to plain HTTP.
    'AUTH_COOKIE_SECURE': not DEBUG,
    'AUTH_COOKIE_HTTP_ONLY': True,
    'AUTH_COOKIE_SAMESITE': 'Lax',
    # A password reset must invalidate existing sessions (spec: password
    # reset). simplejwt's access/refresh tokens are stateless JWTs with no
    # server-side revocation list by default -- adding one (the
    # `token_blacklist` app) would only cover refresh tokens, and only for
    # tokens rotated after enabling it, leaving already-issued access tokens
    # (up to ACCESS_TOKEN_LIFETIME) valid regardless.
    #
    # CHECK_REVOKE_TOKEN is simplejwt's own built-in answer, and covers both
    # token types with no extra infrastructure: every token minted via
    # `Token.for_user()` embeds an MD5 digest of the user's *current* password
    # hash as a claim, and `JWTAuthentication.get_user()` -- the method both
    # `login`/`register`/`refresh` and every authenticated request already go
    # through -- rejects the token the moment that digest stops matching. A
    # password change (`set_password` + `save()`) is exactly such a moment,
    # with no code in this app needing to know it happened. Refreshing an old
    # refresh token still succeeds at the JWT layer (nothing here blacklists
    # it), but the access token it mints carries the same now-stale digest
    # forward, so it is rejected the same way everywhere it is actually used.
    #
    # One side effect worth flagging: this claim is only present on tokens
    # minted after this setting is turned on, so every session that already
    # exists at deploy time is signed out the moment this ships -- a one-time
    # cost, not a per-reset one.
    'CHECK_REVOKE_TOKEN': True,
}

# Where the frontend lives, for link-bearing outgoing messages: the
# password-reset email builds `FRONTEND_BASE_URL + "/reset-password/<token>"`
# (authentication/emails.py) and the invitation-create response builds
# `FRONTEND_BASE_URL + "/invite/<token>"` (tenancy/api/views.py), matching the
# frontend routes at frontend/src/app/reset-password/[token] and
# frontend/src/app/invite/[token].
#
# This is deliberately its own setting, not derived from CORS_ALLOWED_ORIGINS
# below: that list names every origin *permitted* to call the API, not which
# one is *the* frontend, and picking e.g. its first entry would silently
# break the day someone reorders that list.
#
# The default points at the frontend's own local dev address (Next.js's
# default port -- see NEXT_PUBLIC_API_URL's backend-facing counterpart,
# documented in README.md, which points the other way). That default is
# never `None`, on purpose: a link built from `None` would read as
# "None/reset-password/<token>" in a real email, which is worse than the
# bare token this setting replaces. Instead, an unconfigured production
# instance gets a link that is honestly, visibly wrong (it points at
# localhost) rather than silently broken -- the same "obvious placeholder,
# not a silent trap" stance SECRET_KEY's own default takes above: a
# self-hosted instance must set this explicitly for real deployments, same
# as it must set SECRET_KEY.
FRONTEND_BASE_URL = env_base_url('FRONTEND_BASE_URL', 'http://localhost:3000')

# Email (optional): outgoing SMTP for password-reset messages (and any future
# notification). A self-hosted instance must keep working with no mail server
# configured at all -- exactly as it does today -- so every setting here is
# optional and the absence of EMAIL_HOST, not a dedicated on/off flag, is what
# decides whether SMTP is used.
EMAIL_HOST = os.getenv('EMAIL_HOST') or None
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_flag('EMAIL_USE_TLS', True)
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'webmaster@localhost')

# True only when a real mail server is configured -- this is the "operator
# actually did the SMTP setup" signal, independent of which backend Django
# ends up using below.
EMAIL_CONFIGURED = bool(EMAIL_HOST)

if EMAIL_CONFIGURED:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
elif DEBUG:
    # No SMTP and DEBUG on: print the message to the terminal instead of
    # sending it, so the whole password-reset flow is exercisable -- and its
    # exact wording testable -- without ever standing up a mail server.
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # No SMTP and DEBUG off: this is a production instance nobody configured
    # mail for. The console backend would still "work" by printing to stdout,
    # but production stdout is routinely shipped to log aggregators, and a
    # password-reset token is a bearer credential -- logging it anywhere it
    # does not need to be is worse than not sending it at all. The dummy
    # backend discards the message instead, silently and safely.
    EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Whether the password-reset flow is actually usable end to end -- exposed
# through GET /api/v1/auth/config/ so the frontend knows whether to offer a
# "forgot password" link before the visitor can even log in (see
# authentication/views.py:auth_config). Real SMTP makes it usable regardless
# of DEBUG; with no SMTP, DEBUG still makes it usable because the console
# backend prints the message somewhere a developer is expected to be
# looking, but a production instance with no SMTP swallows the message via
# the dummy backend above, so the flow must be reported as unusable there.
EMAIL_USABLE = EMAIL_CONFIGURED or DEBUG

# UUID configuration
DEFAULT_UUID_AUTO_FIELD = 'django.db.models.UUIDField'

# CORS settings
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://localhost:5173,http://localhost:8080'
).split(',')

CORS_ALLOW_CREDENTIALS = True  # Allow cookies to be sent

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-api-key',
]
