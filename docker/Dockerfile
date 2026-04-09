FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend

COPY ui/frontend/package.json ui/frontend/package-lock.json ./
RUN npm ci

COPY ui/frontend/ ./
RUN npm run build

FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.6.17 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/immich-doctor/.venv
ENV PATH="/opt/immich-doctor/.venv/bin:/bin:${PATH}"
ENV IMMICH_DOCTOR_UI_DIST_PATH=/app/ui/dist

WORKDIR /opt/immich-doctor

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid 1000 --create-home --home-dir /home/app --shell /usr/sbin/nologin app

COPY pyproject.toml uv.lock README.md /opt/immich-doctor/
RUN apt-get update && \
    apt-get install -y --no-install-recommends cifs-utils openssh-client postgresql-client rsync && \
    rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --no-install-project

COPY immich_doctor /opt/immich-doctor/immich_doctor
COPY docker/entrypoint.sh /usr/local/bin/immich-doctor-entrypoint
COPY docker/real-storage-cifs-entrypoint.sh /usr/local/bin/immich-doctor-real-storage-entrypoint
COPY --from=frontend-build /frontend/dist /app/ui/dist

RUN sed -i 's/\r$//' /usr/local/bin/immich-doctor-entrypoint && \
    sed -i 's/\r$//' /usr/local/bin/immich-doctor-real-storage-entrypoint && \
    chmod +x /usr/local/bin/immich-doctor-entrypoint /usr/local/bin/immich-doctor-real-storage-entrypoint && \
    mkdir -p \
      /app/ui/dist \
      /opt/immich-doctor/data/reports \
      /opt/immich-doctor/data/manifests \
      /opt/immich-doctor/data/quarantine \
      /opt/immich-doctor/data/logs \
      /opt/immich-doctor/data/tmp \
      /data/reports \
      /data/manifests \
      /data/quarantine \
      /data/logs \
      /data/tmp \
      /config \
      /home/app/.ssh && \
    uv sync --frozen --no-dev && \
    chown -R app:app /app /opt/immich-doctor /data /config

FROM base AS dev

RUN uv sync --frozen --dev

USER app
WORKDIR /workspace

ENTRYPOINT ["immich-doctor-entrypoint"]
CMD ["uv", "run", "python", "-m", "immich_doctor", "--help"]

FROM base AS runtime

USER app
EXPOSE 8000

ENTRYPOINT ["immich-doctor-entrypoint"]
CMD ["uvicorn", "immich_doctor.api:app", "--host", "0.0.0.0", "--port", "8000"]
