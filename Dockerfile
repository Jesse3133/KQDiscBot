# Fiesta KQ Bot container. Data (events, settings, roles) lives in /data, so
# mount a persistent volume there or it's lost whenever the container is rebuilt.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/kqbot.sqlite3

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kqbot ./kqbot

# Runs as root on purpose: hosted volumes (Railway, Fly.io) are mounted
# root-owned, and a non-root user couldn't write the database there.
RUN mkdir -p /data
VOLUME /data

CMD ["python", "-m", "kqbot"]
