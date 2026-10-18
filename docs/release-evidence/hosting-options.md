# Hosted test backend: options (owner decision required)

Status: **proposal only. Nothing is deployed.** Prices are approximate list prices from memory
and MUST be re-checked on each provider's pricing page before a choice is made.

Constraints from the code: single FastAPI container (`Dockerfile`, port 8000, TLS terminated by the
platform, `--proxy-headers`), PostgreSQL (Neon is already provisioned for dev), no Redis dependency
in the request path (rate limit and circuit breaker are in-process, so run **one replica** for the
tester release), secrets via env/secret store, `alembic upgrade head` as a release step.

| Option | Fit | Rough cost (verify) | Notes |
|---|---|---|---|
| Azure Container Apps (consumption) + Neon | Dockerfile and `ops/deploy` already target it | within monthly free grant for a tester load, then pay-per-second; Neon free tier $0 | Scale-to-zero cold starts; pin `minReplicas=1`, `maxReplicas=1` |
| Fly.io (1 shared-cpu VM, 256-512 MB) + Neon | simplest single always-on container, built-in TLS | about $2-5/month | `fly secrets` for keys; one machine |
| Render web service (starter) + Neon | git-less Docker deploy, managed TLS | about $7/month (free tier sleeps) | Free tier sleep breaks first-request latency |
| Railway (hobby) + Neon | quick, usage billed | about $5/month credit-based | Usage-priced; set a spend cap |

Recommendation (conservative): **Fly.io or Azure Container Apps, one replica, Neon free Postgres**,
because the image and runbooks exist for Azure and a single replica keeps the in-process limiter
correct. Model cost stays $0 (free models), but OpenRouter free models allow only 20 requests/minute
and 50/day per key without credits (1000/day with at least $10 credits). That, not hosting, is the
real tester capacity limit: with 50/day the whole tester group shares 50 model replies a day.

Deploy gate checklist (all owner-controlled): choice and approval; production env file passing
`scripts/readiness_config.py` (needs `OPENROUTER` key, reviewed registry path, Clerk keys, finite
budgets, `public_base_url` https); `alembic upgrade head` against the chosen database; TLS and
`/health`, `/ready` observed on the public URL; mobile built with `--dart-define=API_BASE_URL=<url>`.
