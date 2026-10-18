# Hosting the beta test backend

The API is one container (`Dockerfile`, port 8000) plus PostgreSQL. Run **one replica**: the rate
limiter, circuit breaker and model cooldowns are in-process. TLS must be terminated in front of it
(the phone app requires https).

## Option A: Fly.io (about $2-5/month; verify pricing)

```sh
fly launch --no-deploy --dockerfile Dockerfile --internal-port 8000 --name karmi-beta
fly secrets set \
  DAILY_AGENT_ENVIRONMENT=production DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH=false \
  DAILY_AGENT_DATABASE_URL='postgresql+psycopg://…neon…' \
  DAILY_AGENT_AUTH_SECRET="$(openssl rand -hex 32)" DAILY_AGENT_WEBHOOK_SECRET="$(openssl rand -hex 32)" \
  DAILY_AGENT_CLERK_ISSUER=… DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64=… \
  DAILY_AGENT_OPENROUTER_ENABLED=true DAILY_AGENT_OPENROUTER_API_KEY=… \
  DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO=1000000 DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO=1000000
fly deploy --ha=false
fly ssh console -C "alembic upgrade head"
curl https://karmi-beta.fly.dev/ready
```

## Option B: any Linux box with Docker or podman

```sh
cp ops/deploy/.env.example ops/deploy/.env   # fill the required values (never commit it)
docker compose -f ops/deploy/compose.production.example.yaml --env-file ops/deploy/.env up -d --build
docker compose -f ops/deploy/compose.production.example.yaml exec api alembic upgrade head
```
Put Caddy, nginx or a Cloudflare Tunnel in front for https.

## After it is up

Point the app at it: Welcome screen, "Server address", or rebuild with
`python mobile/tool/run_android_dev.py build apk --release --dart-define=API_BASE_URL=https://…`.
Check `scripts/readiness_config.py --env-file <production env> --output out.json`.
