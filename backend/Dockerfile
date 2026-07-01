FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    bash gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# ── Layer 1: heavy/slow wheels cached separately to survive timeouts ──────────
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
    psycopg2-binary==2.9.10 \
    SQLAlchemy==2.0.36 \
    cryptography==43.0.3 \
    pillow \
    reportlab \
    aiohttp \
    uvloop \
    locust==2.32.3

# ── Layer 2: remaining dependencies ──────────────────────────────────────────
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt

COPY . .

# Ensure entrypoint is executable
RUN find /app -name "*.sh" -exec sed -i 's/\r$//' {} \; && chmod +x /app/entrypoint.sh /app/scripts/check_migrations.sh

# Create uploads directory
RUN mkdir -p /app/uploads /app/ml_models

RUN useradd -m -u 1000 vitar && chown -R vitar:vitar /app
USER vitar

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
  CMD curl -f http://localhost:8000/health/ready || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
