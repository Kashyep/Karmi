# Backend API image for Azure Container Apps. No secrets are baked in: all DAILY_AGENT_*
# settings arrive as environment variables (Container Apps secrets via secretref).
FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml requirements.lock README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --no-deps -w /wheels . \
 && pip wheel --no-cache-dir -w /wheels -c requirements.lock /wheels/*.whl

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Uvicorn worker processes per replica. Total DB connections per replica is
# WEB_CONCURRENCY * (DAILY_AGENT_DATABASE_POOL_SIZE + DAILY_AGENT_DATABASE_MAX_OVERFLOW).
# See docs/runbooks/scale.md before raising either value.
ENV WEB_CONCURRENCY=2
RUN useradd --system --uid 10001 --no-create-home karmi
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels daily-agent && rm -rf /wheels
COPY alembic.ini ./
COPY migrations ./migrations
USER karmi
EXPOSE 8000
# exec keeps uvicorn as PID 1 so SIGTERM reaches it for graceful shutdown.
CMD ["sh", "-c", "exec uvicorn daily_agent.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips '*' --timeout-keep-alive 75 --limit-concurrency ${UVICORN_LIMIT_CONCURRENCY:-1000}"]
