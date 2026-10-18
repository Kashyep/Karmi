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
RUN useradd --system --uid 10001 --no-create-home karmi
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels daily-agent && rm -rf /wheels
COPY alembic.ini ./
COPY migrations ./migrations
USER karmi
EXPOSE 8000
CMD ["uvicorn", "daily_agent.api:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
