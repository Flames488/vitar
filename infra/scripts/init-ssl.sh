#!/bin/bash
# init-ssl.sh — Issue a Let's Encrypt certificate for livevault.cloud
# Run ONCE after DNS is pointing to this server.
# Usage: bash infra/scripts/init-ssl.sh

set -euo pipefail

DOMAIN="livevault.cloud"
EMAIL="${CERTBOT_EMAIL:-admin@livevault.cloud}"

GREEN='\033[0;32m'; NC='\033[0m'
log() { echo -e "${GREEN}[SSL]${NC} $1"; }

log "Issuing Let's Encrypt certificate for $DOMAIN, www.$DOMAIN, app.$DOMAIN, and api.$DOMAIN ..."

# Ensure the ACME challenge directory exists
mkdir -p ./infra/nginx/certbot/www/.well-known/acme-challenge

# Start nginx in HTTP-only mode temporarily (for ACME challenge)
docker compose up -d nginx

# Request the certificate (standalone webroot method)
docker run --rm \
  -v "$(pwd)/infra/nginx/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/infra/nginx/certbot/www:/var/www/certbot" \
  certbot/certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN" \
  -d "www.$DOMAIN" \
  -d "app.$DOMAIN" \
  -d "api.$DOMAIN"

log "Certificate issued. Restarting nginx with SSL..."
docker compose restart nginx

log ""
log "SSL is live at https://$DOMAIN"
log ""
log "To auto-renew (add to crontab on the server):"
log "  0 3 * * * docker run --rm -v \$(pwd)/infra/nginx/certbot/conf:/etc/letsencrypt certbot/certbot renew --quiet && docker compose restart nginx"
