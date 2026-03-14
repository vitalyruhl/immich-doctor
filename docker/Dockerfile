FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY immich_doctor /app/immich_doctor

ARG INSTALL_DEV=false

RUN python -m pip install --upgrade pip && \
    if [ "$INSTALL_DEV" = "true" ]; then \
      python -m pip install -e .[dev]; \
    else \
      python -m pip install -e .; \
    fi

ENTRYPOINT ["python", "-m", "immich_doctor"]
CMD ["--help"]

