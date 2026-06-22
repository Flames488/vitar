FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    bash gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
