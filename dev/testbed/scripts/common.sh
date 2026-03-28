#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TESTBED_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$TESTBED_DIR/docker-compose.yml"
ENV_FILE="$TESTBED_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Missing $ENV_FILE. Copy .env.example to .env first." >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Required command not found: $1" >&2
    exit 1
  fi
}

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

db_volume_name() {
  printf '%s\n' "${TESTBED_DB_VOLUME:-immich_dev_pgdata}"
}

snapshot_volume_name() {
  printf '%s\n' "${TESTBED_DB_SNAPSHOT_VOLUME:-immich_dev_pgdata_snapshot}"
}

db_service_name() {
  printf '%s\n' "postgres"
}

db_container_id() {
  compose ps -q "$(db_service_name)"
}

ensure_docker() {
  require_command docker
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not reachable." >&2
    exit 1
  fi
}

ensure_volume_exists() {
  if ! docker volume inspect "$1" >/dev/null 2>&1; then
    echo "Creating Docker volume: $1"
    docker volume create "$1" >/dev/null
  fi
}

confirm_or_exit() {
  prompt="$1"
  force="${2:-false}"
  if [ "$force" = "true" ]; then
    return 0
  fi
  printf '%s [y/N]: ' "$prompt"
  read -r reply
  case "$reply" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      echo "Aborted."
      exit 1
      ;;
  esac
}

wait_for_postgres() {
  max_attempts="${1:-30}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if compose exec -T "$(db_service_name)" pg_isready \
      --dbname="${TESTBED_DB_NAME:-immich}" \
      --username="${TESTBED_DB_USER:-postgres}" >/dev/null 2>&1; then
      echo "PostgreSQL is ready."
      return 0
    fi
    echo "Waiting for PostgreSQL... ($attempt/$max_attempts)"
    attempt=$((attempt + 1))
    sleep 2
  done
  echo "ERROR: PostgreSQL did not become ready in time." >&2
  exit 1
}

copy_volume_contents() {
  src_volume="$1"
  dest_volume="$2"
  ensure_volume_exists "$src_volume"
  ensure_volume_exists "$dest_volume"
  docker run --rm \
    -v "${src_volume}:/from:ro" \
    -v "${dest_volume}:/to" \
    alpine:3.20 \
    sh -eu -c '
      mkdir -p /to
      find /to -mindepth 1 -maxdepth 1 -exec rm -rf {} +
      cd /from
      tar cpf - . | tar xpf - -C /to
    '
}

restore_dump_into_database() {
  dump_path="$1"
  dump_format="$2"
  container_id=$(db_container_id)
  if [ -z "$container_id" ]; then
    echo "ERROR: PostgreSQL container is not running." >&2
    exit 1
  fi
  if [ ! -f "$dump_path" ]; then
    echo "ERROR: Dump file not found: $dump_path" >&2
    exit 1
  fi

  container_dump_path="/tmp/immich-testbed.dump"
  echo "Copying dump into container..."
  docker cp "$dump_path" "${container_id}:${container_dump_path}"

  echo "Recreating target database..."
  compose exec -T "$(db_service_name)" sh -eu -c "
    psql --username='${TESTBED_DB_USER:-postgres}' --dbname=postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${TESTBED_DB_NAME:-immich}' AND pid <> pg_backend_pid();\" >/dev/null
    dropdb --if-exists --force --username='${TESTBED_DB_USER:-postgres}' '${TESTBED_DB_NAME:-immich}'
    createdb --username='${TESTBED_DB_USER:-postgres}' '${TESTBED_DB_NAME:-immich}'
  "

  case "$dump_format" in
    auto)
      case "$dump_path" in
        *.dump|*.backup|*.bin)
          dump_format="custom"
          ;;
        *.sql)
          dump_format="plain"
          ;;
        *)
          echo "ERROR: Could not infer dump format for $dump_path. Set TESTBED_DUMP_FORMAT to plain or custom." >&2
          exit 1
          ;;
      esac
      ;;
  esac

  echo "Restoring database using format: $dump_format"
  case "$dump_format" in
    custom)
      compose exec -T "$(db_service_name)" pg_restore \
        --clean \
        --if-exists \
        --no-owner \
        --no-privileges \
        --username="${TESTBED_DB_USER:-postgres}" \
        --dbname="${TESTBED_DB_NAME:-immich}" \
        "$container_dump_path"
      ;;
    plain)
      compose exec -T "$(db_service_name)" sh -eu -c "
        psql --username='${TESTBED_DB_USER:-postgres}' --dbname='${TESTBED_DB_NAME:-immich}' -f '$container_dump_path'
      "
      ;;
    *)
      echo "ERROR: Unsupported dump format: $dump_format" >&2
      exit 1
      ;;
  esac

  compose exec -T "$(db_service_name)" rm -f "$container_dump_path"
  echo "Database restore completed."
}
