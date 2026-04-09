#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TESTBED_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$TESTBED_DIR/docker-compose.yml"
ENV_FILE="$TESTBED_DIR/.env"
ENV_LOCAL_FILE="$TESTBED_DIR/.env.local"
INITIAL_ENV_VARS=$(env | sed 's/=.*//')

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Missing $ENV_FILE. Copy .env.example to .env first." >&2
  exit 1
fi

set -a
import_testbed_env() {
  file_path="$1"
  [ -f "$file_path" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    trimmed=$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -n "$trimmed" ] || continue
    case "$trimmed" in
      \#*) continue ;;
    esac
    key=${trimmed%%=*}
    value=${trimmed#*=}
    if printf '%s\n' "$INITIAL_ENV_VARS" | grep -Fxq "$key"; then
      continue
    fi
    export "$key=$value"
  done < "$file_path"
}

import_testbed_env "$ENV_FILE"
import_testbed_env "$ENV_LOCAL_FILE"
set +a

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Required command not found: $1" >&2
    exit 1
  fi
}

compose() {
  if [ -f "$ENV_LOCAL_FILE" ]; then
    docker compose --env-file "$ENV_FILE" --env-file "$ENV_LOCAL_FILE" -f "$COMPOSE_FILE" "$@"
  else
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  fi
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

volume_exists() {
  docker volume inspect "$1" >/dev/null 2>&1
}

ensure_volume_exists() {
  volume_name="$1"
  label="${2:-Docker volume}"
  if volume_exists "$volume_name"; then
    echo "$label already exists: $volume_name"
    return 0
  fi
  echo "Creating $label: $volume_name"
  docker volume create "$volume_name" >/dev/null
}

require_volume() {
  volume_name="$1"
  label="${2:-Docker volume}"
  if ! volume_exists "$volume_name"; then
    echo "ERROR: $label does not exist: $volume_name" >&2
    exit 1
  fi
  echo "$label exists: $volume_name"
}

remove_volume_if_exists() {
  volume_name="$1"
  label="${2:-Docker volume}"
  if ! volume_exists "$volume_name"; then
    echo "$label already absent: $volume_name"
    return 0
  fi
  echo "Removing $label: $volume_name"
  docker volume rm -f "$volume_name" >/dev/null
}

resolve_host_path() {
  path_value="$1"
  case "$path_value" in
    /*)
      printf '%s\n' "$path_value"
      ;;
    [A-Za-z]:/*)
      printf '%s\n' "$path_value"
      ;;
    *)
      printf '%s/%s\n' "$TESTBED_DIR" "$path_value"
      ;;
  esac
}

resolve_selected_storage_path() {
  mode="${TESTBED_STORAGE_SOURCE_MODE:-mock}"
  case "$mode" in
    mock)
      path_value="${TESTBED_MOCK_STORAGE_PATH:-../../data/mock/immich-library}"
      ;;
    real)
      path_value="${TESTBED_REAL_STORAGE_PATH:-}"
      if [ -z "$path_value" ]; then
        echo "ERROR: TESTBED_REAL_STORAGE_PATH is required when TESTBED_STORAGE_SOURCE_MODE=real." >&2
        exit 1
      fi
      ;;
    *)
      echo "ERROR: Unsupported TESTBED_STORAGE_SOURCE_MODE '$mode'. Use mock or real." >&2
      exit 1
      ;;
  esac
  TESTBED_SELECTED_STORAGE_PATH=$(resolve_host_path "$path_value")
  export TESTBED_SELECTED_STORAGE_PATH
}

resolve_selected_storage_path

resolve_dump_mount_source() {
  dump_path="${TESTBED_DUMP_PATH:-}"
  if [ -z "$dump_path" ]; then
    TESTBED_DUMP_MOUNT_SOURCE="$TESTBED_DIR/tmp"
    export TESTBED_DUMP_MOUNT_SOURCE
    return
  fi
  resolved_dump_path=$(resolve_host_path "$dump_path")
  TESTBED_DUMP_MOUNT_SOURCE=$(dirname "$resolved_dump_path")
  export TESTBED_DUMP_MOUNT_SOURCE
}

resolve_dump_mount_source

default_export_path() {
  format="${1:-custom}"
  case "$format" in
    plain)
      printf '%s/exports/immich-testbed-export.sql\n' "$TESTBED_DIR"
      ;;
    *)
      printf '%s/exports/immich-testbed-export.dump\n' "$TESTBED_DIR"
      ;;
  esac
}

resolve_dump_format() {
  dump_path="$1"
  dump_format="$2"
  case "$dump_format" in
    auto)
      case "$dump_path" in
        *.dump|*.backup|*.bin)
          printf '%s\n' "custom"
          ;;
        *.sql)
          printf '%s\n' "plain"
          ;;
        *)
          echo "ERROR: Could not infer dump format for $dump_path. Set TESTBED_DUMP_FORMAT to plain or custom." >&2
          exit 1
          ;;
      esac
      ;;
    *)
      printf '%s\n' "$dump_format"
      ;;
  esac
}

is_plain_sql_cluster_dump() {
  dump_path="$1"
  tr -d '\r' < "$dump_path" | head -n 80 | grep -q "PostgreSQL database cluster dump"
}

ensure_parent_directory() {
  output_path="$1"
  parent_dir=$(dirname "$output_path")
  if [ ! -d "$parent_dir" ]; then
    echo "Creating directory: $parent_dir"
    mkdir -p "$parent_dir"
  fi
}

copy_volume_contents() {
  src_volume="$1"
  dest_volume="$2"
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

database_exists() {
  db_name="$1"
  result=$(compose exec -T "$(db_service_name)" psql \
    --username="${TESTBED_DB_USER:-postgres}" \
    --dbname=postgres \
    -Atqc "SELECT 1 FROM pg_database WHERE datname = '$db_name';" 2>/dev/null || true)
  [ "$result" = "1" ]
}

restore_dump_into_database() {
  dump_path="$1"
  dump_format="$2"
  resolved_dump_path=$(resolve_host_path "$dump_path")
  resolved_dump_format=$(resolve_dump_format "$resolved_dump_path" "$dump_format")
  container_id=$(db_container_id)
  if [ -z "$container_id" ]; then
    echo "ERROR: PostgreSQL container is not running." >&2
    exit 1
  fi
  if [ ! -f "$resolved_dump_path" ]; then
    echo "ERROR: Dump file not found: $resolved_dump_path" >&2
    exit 1
  fi

  container_dump_path="/tmp/immich-testbed.dump"
  container_prepared_dump_path="/tmp/immich-testbed-prepared.sql"
  container_restore_log_path="/tmp/immich-testbed-restore.log"
  host_prepared_dump=""
  host_skip_count=""

  echo "Copying dump into container..."
  docker cp "$resolved_dump_path" "${container_id}:${container_dump_path}"

  restore_output_file=$(mktemp)
  classification="failure"
  meaningful_error_count=0
  structural_error_count=0
  expected_skipped_statements=0

  case "$resolved_dump_format" in
    custom)
      echo "Recreating target database for custom-format restore..."
      compose exec -T "$(db_service_name)" sh -eu -c "
        psql --username='${TESTBED_DB_USER:-postgres}' --dbname=postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${TESTBED_DB_NAME:-immich}' AND pid <> pg_backend_pid();\" >/dev/null
        dropdb --if-exists --force --username='${TESTBED_DB_USER:-postgres}' '${TESTBED_DB_NAME:-immich}'
        createdb --username='${TESTBED_DB_USER:-postgres}' '${TESTBED_DB_NAME:-immich}'
      "
      echo "Restoring database using format: custom"
      set +e
      compose exec -T "$(db_service_name)" sh -eu -c "
        pg_restore --clean --if-exists --no-owner --no-privileges --username='${TESTBED_DB_USER:-postgres}' --dbname='${TESTBED_DB_NAME:-immich}' '$container_dump_path' > '$container_restore_log_path' 2>&1
        status=\$?
        grep -E 'ERROR:|FATAL:' '$container_restore_log_path' || true
        exit \$status
      " >"$restore_output_file" 2>&1
      restore_status=$?
      set -e
      cat "$restore_output_file"
      meaningful_error_count=$(grep -ci 'error:' "$restore_output_file" || true)
      structural_error_count=0
      wait_for_postgres
      if [ "$restore_status" -ne 0 ] || ! database_exists "${TESTBED_DB_NAME:-immich}"; then
        classification="failure"
      elif [ "$meaningful_error_count" -gt 0 ]; then
        classification="partial success"
      else
        classification="success"
      fi
      ;;
    plain)
      if is_plain_sql_cluster_dump "$resolved_dump_path"; then
        echo "Detected plain SQL cluster dump. Restoring from maintenance database without pre-creating the target DB."
        host_prepared_dump=$(mktemp)
        host_skip_count=$(mktemp)
        awk -v bootstrap_role="${TESTBED_DB_USER:-postgres}" -v skip_file="$host_skip_count" '
BEGIN { skipped=0 }
{
  sub(/\r$/, "")
  if ($0 == "DROP ROLE IF EXISTS " bootstrap_role ";") { print "-- immich-doctor skipped bootstrap role drop: " $0; skipped++; next }
  if ($0 == "CREATE ROLE " bootstrap_role ";") { print "-- immich-doctor skipped bootstrap role create: " $0; skipped++; next }
  if ($0 ~ ("^ALTER ROLE " bootstrap_role " WITH ")) { print "-- immich-doctor skipped bootstrap role alter: " $0; skipped++; next }
  print
}
END { print skipped > skip_file }
' "$resolved_dump_path" > "$host_prepared_dump"
        docker cp "$host_prepared_dump" "${container_id}:${container_prepared_dump_path}"
        expected_skipped_statements=$(cat "$host_skip_count")
        [ -n "$expected_skipped_statements" ] || expected_skipped_statements=0
        if [ "$expected_skipped_statements" -gt 0 ]; then
          echo "Skipped bootstrap-role statements for the active testbed login role: $expected_skipped_statements"
        fi
        echo "Restoring database using format: plain (cluster-aware mode)"
        set +e
        compose exec -T "$(db_service_name)" sh -eu -c "
          psql --username='${TESTBED_DB_USER:-postgres}' --dbname=postgres -v ON_ERROR_STOP=0 -f '$container_prepared_dump_path' > '$container_restore_log_path' 2>&1
          status=\$?
          grep -E 'ERROR:|FATAL:' '$container_restore_log_path' || true
          exit \$status
        " >"$restore_output_file" 2>&1
        restore_status=$?
        set -e
      else
        echo "Detected plain SQL database dump. Recreating target database before restore."
        compose exec -T "$(db_service_name)" sh -eu -c "
          psql --username='${TESTBED_DB_USER:-postgres}' --dbname=postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${TESTBED_DB_NAME:-immich}' AND pid <> pg_backend_pid();\" >/dev/null
          dropdb --if-exists --force --username='${TESTBED_DB_USER:-postgres}' '${TESTBED_DB_NAME:-immich}'
          createdb --username='${TESTBED_DB_USER:-postgres}' '${TESTBED_DB_NAME:-immich}'
        "
        echo "Restoring database using format: plain (database-only mode)"
        set +e
        compose exec -T "$(db_service_name)" sh -eu -c "
          psql --username='${TESTBED_DB_USER:-postgres}' --dbname='${TESTBED_DB_NAME:-immich}' -v ON_ERROR_STOP=0 -f '$container_dump_path' > '$container_restore_log_path' 2>&1
          status=\$?
          grep -E 'ERROR:|FATAL:' '$container_restore_log_path' || true
          exit \$status
        " >"$restore_output_file" 2>&1
        restore_status=$?
        set -e
      fi

      cat "$restore_output_file"
      meaningful_error_count=$(grep -ci 'error:' "$restore_output_file" || true)
      structural_error_count=0
      for pattern in \
        "cannot drop the currently open database" \
        "current user cannot be dropped" \
        "role \"${TESTBED_DB_USER:-postgres}\" already exists" \
        "database \"${TESTBED_DB_NAME:-immich}\" already exists"
      do
        matches=$(grep -Fic "$pattern" "$restore_output_file" || true)
        structural_error_count=$((structural_error_count + matches))
      done
      wait_for_postgres
      if [ "$restore_status" -ne 0 ] || [ "$structural_error_count" -gt 0 ] || ! database_exists "${TESTBED_DB_NAME:-immich}"; then
        classification="failure"
      elif [ "$meaningful_error_count" -gt 0 ]; then
        classification="partial success"
      else
        classification="success"
      fi
      ;;
    *)
      rm -f "$restore_output_file"
      echo "ERROR: Unsupported dump format: $resolved_dump_format" >&2
      exit 1
      ;;
  esac

  echo "Restore classification: $classification"
  if [ "$expected_skipped_statements" -gt 0 ]; then
    echo "Expected skipped statements: $expected_skipped_statements"
  fi
  if [ "$structural_error_count" -gt 0 ]; then
    echo "Structural restore errors: $structural_error_count"
  fi
  if [ "$meaningful_error_count" -gt 0 ]; then
    echo "Meaningful restore errors: $meaningful_error_count"
  fi

  compose exec -T "$(db_service_name)" rm -f "$container_dump_path" "$container_prepared_dump_path" "$container_restore_log_path" >/dev/null 2>&1 || true
  [ -n "$host_prepared_dump" ] && rm -f "$host_prepared_dump"
  [ -n "$host_skip_count" ] && rm -f "$host_skip_count"
  rm -f "$restore_output_file"

  if [ "$classification" = "failure" ]; then
    echo "ERROR: Restore classification: failure" >&2
    exit 1
  fi
}
