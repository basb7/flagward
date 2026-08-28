FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Dependency manifests only, so dependency layers are cached independently
# of the application source.
COPY requirements/ /app/requirements/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/')" || exit 1


# Development image: includes test and lint dependencies. Compose mounts the
# working tree over /app, so the source copied here is only a fallback.
FROM base AS dev

RUN pip install -r requirements/dev.txt

COPY . /app/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


# Production image: runtime dependencies only, no test or lint tooling,
# running as an unprivileged user.
FROM base AS prod

RUN pip install -r requirements/base.txt

RUN adduser --system --group --no-create-home app

COPY --chown=app:app . /app/

USER app

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
