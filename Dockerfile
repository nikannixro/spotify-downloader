FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p cache data logs /tmp/ytdl

RUN useradd -m -r -s /bin/bash botuser && \
    chown -R botuser:botuser /app /tmp/ytdl
USER botuser

VOLUME ["/app/data", "/app/cache"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('data/database.db').execute('SELECT 1').fetchone()" || exit 1

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
