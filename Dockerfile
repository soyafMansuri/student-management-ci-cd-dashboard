FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Non-root user (uid 1000) owns the app and the /data directory
RUN groupadd --system --gid 1000 appuser \
 && useradd --system --uid 1000 --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY dashboard ./dashboard
COPY wsgi.py .

# /data holds the SQLite database. docker-compose mounts a named volume here.
RUN mkdir -p /data && chown appuser:appuser /data

# Build-time version label only (a commit SHA). No secrets are baked into the image.
ARG GIT_SHA=dev
ENV APP_VERSION=${GIT_SHA} \
    DATABASE_PATH=/data/students.db

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Access log omits query strings so search terms are not logged.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--access-logformat", "%(h)s \"%(m)s %(U)s\" %(s)s %(L)s", "wsgi:app"]
