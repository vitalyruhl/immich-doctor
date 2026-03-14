FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.6.17 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/immich-doctor/.venv
ENV PATH="/opt/immich-doctor/.venv/bin:/bin:${PATH}"

WORKDIR /opt/immich-doctor

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid 1000 --create-home --home-dir /home/app --shell /usr/sbin/nologin app

COPY pyproject.toml uv.lock README.md /opt/immich-doctor/
RUN uv sync --frozen --no-dev --no-install-project

COPY immich_doctor /opt/immich-doctor/immich_doctor
COPY docker/entrypoint.sh /usr/local/bin/immich-doctor-entrypoint

RUN chmod +x /usr/local/bin/immich-doctor-entrypoint && \
    mkdir -p \
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
      /config && \
    uv sync --frozen --no-dev && \
    chown -R app:app /opt/immich-doctor /data /config

FROM base AS dev

RUN uv sync --frozen --dev

USER app
WORKDIR /workspace

ENTRYPOINT ["immich-doctor-entrypoint"]
CMD ["uv", "run", "python", "-m", "immich_doctor", "--help"]

FROM base AS runtime

USER app

ENTRYPOINT ["immich-doctor-entrypoint"]
CMD ["sh", "-c", "python -m immich_doctor runtime validate && exec sleep infinity"]
