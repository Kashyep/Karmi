# Hosting the beta test backend

The API is one container (`Dockerfile`, port 8000) plus PostgreSQL. Run **one replica**: the rate
limiter, circuit breaker and model cooldowns are in-process. TLS must be terminated in front of it
(the phone app requires https).

## Azure App Service (beta)

Deploy using Azure App Service with an external Postgres database. The service listens on port 8000. TLS ingress must be configured upstream. Student Azure accounts do NOT allow ACR Tasks, so local images must be built and pushed manually.

1. Build the backend container image locally for linux/amd64:
   
   ```sh
   podman build --platform=linux/amd64 -t karmi-backend .
   az acr login --name karmiacr
   podman tag karmi-backend karmiacr.azurecr.io/karmi-backend:latest
   podman push karmiacr.azurecr.io/karmi-backend:latest
   ```

2. Use the deploy script for migration, build, and deploy steps:

   ```sh
   ~/.venvs/karmi/bin/python scripts/deploy_azure.py migrate   # Run Alembic DB migrations
   ~/.venvs/karmi/bin/python scripts/deploy_azure.py build     # Tag and push image (as above)
   ~/.venvs/karmi/bin/python scripts/deploy_azure.py deploy    # Deploys container, creates mode-600 .env.azure.prod
   ~/.venvs/karmi/bin/python scripts/deploy_azure.py status    # Show latest deploy details
   ```

   - RG: `rg-karmi-prod`, App: `karmi-beta`, CAE: `cae-karmi-prod`, Region: `eastasia`, port: 8000

3. Environment: The script writes the secrets to `.env.azure.prod` (mode 600, ignored).

4. Never commit or expose secrets or .env.* files.

For readiness and more, see [`docs/runbooks/azure-deployment.md`](../../docs/runbooks/azure-deployment.md).


## After it is up

Point the app at it: Welcome screen, "Server address", or rebuild with
`python mobile/tool/run_android_dev.py build apk --release --dart-define=API_BASE_URL=https://…`.
Check `scripts/readiness_config.py --env-file <production env> --output out.json`.
