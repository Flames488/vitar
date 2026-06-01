# Deploying to labvault.cloud

No subdomain. Everything runs on **https://labvault.cloud**.

---

## Prerequisites

- A Linux VPS (Ubuntu 22.04+ recommended) with Docker and Docker Compose v2 installed
- DNS A record: `labvault.cloud → <your server IP>`
- DNS A record: `www.labvault.cloud → <your server IP>`
- Port 80 and 443 open in your firewall

---

## Step 1 — Upload the project

```bash
scp vitar_v5_1_labvault.zip user@<your-server-ip>:~
ssh user@<your-server-ip>
unzip vitar_v5_1_labvault.zip
cd vitar_v5_final
```

---

## Step 2 — Generate your .env

```bash
bash generate_env.sh
```

This creates `.env` with random secrets already set for `labvault.cloud`.
Then open `.env` and fill in your external service keys:

```
PAYSTACK_SECRET_KEY=sk_live_...      # or STRIPE_SECRET_KEY
PAYSTACK_WEBHOOK_SECRET=...
SENDGRID_API_KEY=SG...
TERMII_API_KEY=...                   # for SMS in Nigeria
```

---

## Step 3 — Issue your SSL certificate

```bash
# Set your email for Let's Encrypt expiry notices
export CERTBOT_EMAIL=you@labvault.cloud

bash infra/scripts/init-ssl.sh
```

This issues a free certificate for `labvault.cloud` and `www.labvault.cloud`.
Takes about 30 seconds. Only needs to be run once.

---

## Step 4 — Start everything

```bash
bash infra/scripts/setup.sh prod
```

This builds all images, runs database migrations, and starts all services.

---

## Step 5 — Verify

```bash
# All services should show healthy/running
docker compose ps

# API health check
curl https://labvault.cloud/health

# Logs
docker compose logs api --tail=50
```

---

## SSL Auto-Renewal

Let's Encrypt certificates expire every 90 days. Add this to cron on the server (`crontab -e`):

```
0 3 * * * cd /path/to/vitar_v5_final && docker run --rm -v $(pwd)/infra/nginx/certbot/conf:/etc/letsencrypt certbot/certbot renew --quiet && docker compose restart nginx
```

---

## Updating the app

```bash
git pull   # or re-upload zip
docker compose build api worker worker_dead_letter beat frontend
docker compose up -d
```

---

## Flower (Celery monitor)

Flower is bound to `127.0.0.1:5555` — not public. Access via SSH tunnel:

```bash
ssh -L 5555:localhost:5555 user@<your-server-ip>
# Then open http://localhost:5555 in your browser
```

Credentials are in `.env` as `FLOWER_USER` and `FLOWER_PASSWORD`.
