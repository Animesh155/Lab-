# Lab 3 — chemical-plant tabletop simulator. Single-replica FastAPI + WebSocket
# server. Designed for AWS ECS / Fargate (or any container-as-a-service that
# supports WebSockets with sticky sessions).
#
# Build:
#   docker build -t lab3 -f Dockerfile .   (run from this directory)
#
# Run locally:
#   docker run --rm -p 8080:8080 \
#     -e LAB3_INSTRUCTOR_TOKEN=test123 \
#     -v $(pwd)/local_events:/data/events \
#     lab3
#
# In production (ECS Fargate):
#   - Mount an EFS volume at /data/events for durable session logs.
#   - Set LAB3_INSTRUCTOR_TOKEN to a strong secret via Secrets Manager.
#   - Put the task behind an ALB with WS listener + cookie stickiness.

FROM python:3.12-slim

# Run as non-root for the cloud — Fargate enforces this in many configs.
RUN useradd --create-home --shell /bin/bash lab3
WORKDIR /app

# Install Python deps first so layer cache survives source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the lab3 package itself.  The build context is the lab3 directory, so
# `.` here means everything in phase1_env/lab3/ (engine/, server/, web/,
# config/, data/, etc.). `.dockerignore` filters out tests/, events/, caches.
COPY . /app/phase1_env/lab3/
RUN touch /app/phase1_env/__init__.py /app/phase1_env/lab3/__init__.py \
 && mkdir -p /data/events \
 && chown -R lab3:lab3 /app /data

USER lab3

ENV PYTHONPATH=/app \
    LAB3_EVENTS_DIR=/data/events \
    PORT=8080

EXPOSE 8080

# Liveness probe for ECS / ALB. `/api/instructor/state` is auth-gated, so use
# the root index.html instead — it's static and proves the app loop is alive.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/', timeout=2).status == 200 else 1)" || exit 1

CMD ["sh", "-c", "uvicorn phase1_env.lab3.server.app:app --host 0.0.0.0 --port ${PORT}"]
