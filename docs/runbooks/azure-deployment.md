# Azure Beta Deployment Runbook

This guide details deploying the karmi-beta backend using Azure App Service and ACR, with local Podman builds required for Student subscriptions.

## Prerequisites
- Azure CLI, Podman, and Docker (alternative only if Podman unavailable)
- IAM access to Azure subscription and `karmi-backend` ACR repo

## Build and Publishing Image
Due to Azure for Students disallowing ACR Tasks, manually build and push:

```sh
podman build --platform=linux/amd64 -t karmi-backend .
az acr login --name karmiacr
podman tag karmi-backend karmiacr.azurecr.io/karmi-backend:latest
podman push karmiacr.azurecr.io/karmi-backend:latest
```

## Scripted Deploy Steps
Run commands from project root (activate venv with required dependencies):
- `~/.venvs/karmi/bin/python scripts/deploy_azure.py migrate` — Apply Alembic DB migrations
- `~/.venvs/karmi/bin/python scripts/deploy_azure.py build` — Tag & push image (as above)
- `~/.venvs/karmi/bin/python scripts/deploy_azure.py deploy` — Deploys image & writes mode-600 .env.azure.prod
- `~/.venvs/karmi/bin/python scripts/deploy_azure.py status` — Show current deploy details

Values hardcoded for prod:
- Resource group: `rg-karmi-prod`
- App: `karmi-beta`
- Container App Environment: `cae-karmi-prod`
- Region: `eastasia`
- Port: 8000 (external ingress)

## Safe Secrets Handling
- NEVER commit or expose secrets or any .env.* file to VCS or logs.
- The deploy script emits secrets to `.env.azure.prod` (mode 600, in .gitignore).
- Inspect environment with extreme care downstream.

## Readiness Check
Use `scripts/readiness_config.py --env-file .env.azure.prod --output out.json` to generate health config post-deploy.

## Audit/Issues Checklist (if unable to complete)
- If ACR push, deploy, or migration steps fail, review Azure quotas, credential, and Podman install.
- Only manual image builds/pushes allowed under Student plan.

---
For further issues, see team SRE contact or Azure Portal for diagnostics.
