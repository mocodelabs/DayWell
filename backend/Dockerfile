# DayWell backend image (API, Celery worker and Celery beat all use this image with different commands).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client curl tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 daywell

WORKDIR /app
COPY requirements.txt requirements.lock ./
# requirements.lock pins the exact versions the test suite was run against.
RUN pip install -r requirements.txt -c requirements.lock

COPY . .
# collectstatic needs a syntactically valid secret; the real one is supplied at runtime.
RUN DJANGO_SECRET_KEY=build-only-placeholder-secret-key-not-used-at-runtime-000 DATABASE_URL=postgres://x:x@localhost/x \
    python manage.py collectstatic --noinput

USER daywell
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8000/health/live/ || exit 1
# Threaded workers: requests spend much of their time waiting on PostgreSQL, so threads raise concurrency cheaply.
# Size with GUNICORN_WORKERS (≈ CPU cores) × GUNICORN_THREADS; each thread may hold one DB connection.
ENV GUNICORN_WORKERS=4 GUNICORN_THREADS=4
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers ${GUNICORN_WORKERS} --threads ${GUNICORN_THREADS} --timeout 30 --access-logfile -"]
