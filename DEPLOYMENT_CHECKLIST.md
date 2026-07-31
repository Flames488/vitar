# Vitar → livevault.cloud: InterServer + Cloudflare Deploy Checklist

Your stack already includes Postgres, Redis, PgBouncer, API, worker, worker_dead_letter,
beat, Flower, frontend, nginx, Prometheus, Alertmanager, Grafana, and two exporters —
12+ containers. Size the VPS for that, not for a static site.

## Phase 0 — Provision the InterServer VPS (1-slice pilot tier)

**This is a bootstrap plan, not the full-scale one.** You're starting with a few pilot
clinics, not 10,000 users — so we're deploying `docker-compose.prod-free.yml`, a trimmed
version of the stack: no local Postgres container (uses a free Supabase database
instead), no Prometheus/Grafana/observability stack, Flower disabled by default, frontend
built as static files served directly by nginx. Once you've onboarded clinics and have
investor money, upgrading to more slices and the full `docker-compose.prod.yml` stack is
a resize + `docker compose down && docker compose -f docker-compose.prod.yml up -d` away
— no rewrite needed.

1. Order **1 slice** ($3/mo, 1 vCPU / 2048MB RAM / 40GB storage) at interserver.net.
2. OS: **Ubuntu 24.04 LTS**. Location: **New Jersey** (InterServer's only options are
   US-based — NJ, LA, Texas — NJ has the best general routing toward Africa/Europe of
   the three).
3. Add your SSH public key during provisioning if offered.

**Sign up for Supabase** (free tier — 500MB DB, more than enough for a pilot):
supabase.com → new project → note down the DB host, password, and connection string.
These go into `.env` as `SUPABASE_DB_HOST`, `SUPABASE_DB_PASSWORD`, `SUPABASE_DB_URL`.

**Add a 2GB swap file** — with only 2048MB RAM and ~1.6GB already budgeted across
containers, a swap file is cheap insurance against an OOM kill during a traffic spike,
not a performance crutch:
```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab   # persists across reboots
```

## Phase 1 — DNS + Cloudflare

1. Add `livevault.cloud` as a site in Cloudflare (free plan is fine).
2. Cloudflare will give you two nameservers — set those at your domain registrar.
3. In Cloudflare DNS, add:
   - `A livevault.cloud → <VPS IP>` — proxy status **ON** (orange cloud)
   - `A www.livevault.cloud → <VPS IP>` — proxy status **ON**
4. SSL/TLS mode: set to **Full (strict)** once your origin cert is issued in Phase 3
   (use "Full" temporarily until then — never "Flexible", it causes redirect loops
   with apps that already redirect HTTP→HTTPS).

## Phase 2 — Server setup

```bash
ssh root@<VPS IP>
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 ufw fail2ban unattended-upgrades
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
systemctl enable fail2ban --now
dpkg-reconfigure -plow unattended-upgrades   # confirm "Yes" — auto-installs security patches
```

⚠️ **Fill in the Supabase and domain values** added to `.env.example` above:
`DOMAIN`, `SUPABASE_DB_HOST`, `SUPABASE_DB_PASSWORD`, `SUPABASE_DB_URL`, `FLOWER_USER`,
`FLOWER_PASSWORD`. (`UVICORN_WORKERS` is hardcoded to 2 directly inside
`docker-compose.prod-free.yml` for this tier — nothing to set for it in `.env`.)

Build the frontend as static files — this compose variant has no frontend container,
nginx serves the built files directly:
```bash
cd frontend
npm install
npm run build      # outputs to frontend/dist
cd ..
```

## Phase 3 — Upload code and configure

```bash
# from your local machine
scp -r vitar_v11_final root@<VPS IP>:~
ssh root@<VPS IP>
cd vitar_v11_final
bash generate_env.sh          # generates .env with secrets pre-set for livevault.cloud
nano .env                     # fill in PAYSTACK_SECRET_KEY, PAYSTACK_WEBHOOK_SECRET,
                               # SENDGRID_API_KEY, TERMII_API_KEY
```

Fetch Cloudflare's current IP ranges (needed before nginx starts, so rate limiting
sees real visitor IPs instead of Cloudflare's edge IPs):

```bash
bash infra/scripts/update-cloudflare-ips.sh
```

Issue your origin SSL cert (works even behind Cloudflare proxy — Let's Encrypt's
HTTP-01 challenge passes through):

```bash
export CERTBOT_EMAIL=you@livevault.cloud
bash infra/scripts/init-ssl.sh
```

## Phase 4 — Bring the stack up

`infra/scripts/setup.sh` only supports the full `docker-compose.prod.yml` stack, so for
this pilot tier, bring it up directly with `docker-compose.prod-free.yml`:

```bash
# Run migrations against Supabase once
docker compose -f docker-compose.prod-free.yml run --rm api alembic upgrade head

# Start everything (Flower stays off by default — see Phase 0 note)
docker compose -f docker-compose.prod-free.yml up -d --build

docker compose -f docker-compose.prod-free.yml ps      # everything should show healthy
curl https://livevault.cloud/health
docker compose -f docker-compose.prod-free.yml logs api --tail=50
```

Switch Cloudflare SSL/TLS mode to **Full (strict)** now that the origin cert exists.

## Phase 5 — Cron jobs on the VPS

```bash
crontab -e
```
Add:
```
# Let's Encrypt renewal (every 90 days, checked daily)
0 3 * * * cd /root/vitar_v11_final && docker run --rm -v $(pwd)/infra/nginx/certbot/conf:/etc/letsencrypt certbot/certbot renew --quiet && docker compose -f docker-compose.prod-free.yml restart nginx

# Refresh Cloudflare IP ranges monthly (they change occasionally)
0 4 1 * * cd /root/vitar_v11_final && bash infra/scripts/update-cloudflare-ips.sh && docker compose -f docker-compose.prod-free.yml exec nginx nginx -s reload
```

## Phase 6 — Test before announcing

This is where Paystack live testing finally becomes possible — webhooks only fire to
the production URL, so this couldn't be tested locally.

- [ ] Register a test clinic end-to-end
- [ ] Book a test appointment as a patient, pay with a real small amount via Paystack
- [ ] Confirm the webhook fires and marks the appointment paid (check `docker compose logs worker`)
- [ ] Confirm the Celery beat auto-transfer fallback fires correctly for hospital payout
- [ ] Check backend logs are readable and useful: `docker compose -f docker-compose.prod-free.yml logs -f api worker` (no Grafana on this tier — Sentry, which is external/off-box, is still active for error tracking)
- [ ] Trigger a rate-limit test (rapid requests to `/api/v1/auth/login`) and confirm it's
      keyed per real visitor IP, not collapsing all Cloudflare traffic into one bucket
- [ ] Check `docker stats` under a burst of test traffic — confirm no container is
      hitting its memory limit and getting OOM-killed

## Notes

- This pilot-tier deploy uses `docker-compose.prod-free.yml`, not `docker-compose.prod.yml`
  — deliberately trimmed to fit a $3/mo, 2GB slice: Supabase instead of a local Postgres
  container, no Prometheus/Grafana/Alertmanager, Flower off by default, static frontend.
- **Upgrade path, once you've onboarded clinics and raised funding:** add InterServer
  slices (resize, no rebuild needed), then switch to `docker-compose.prod.yml` for the
  full stack (local Postgres, full observability, Flower on) — `UVICORN_WORKERS` in that
  file should then match your new vCPU count.
- Flower and (on the full-tier stack) Grafana are bound to localhost only — access via
  SSH tunnel, never open those ports in `ufw`.
