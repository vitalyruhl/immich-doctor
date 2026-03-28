#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

OUTPUT_PATH="${TESTBED_EXPORT_PATH:-}"
FORMAT="custom"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --format)
      FORMAT="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: export-db.sh [--output /path/to/file] [--format custom|plain]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -n "$OUTPUT_PATH" ]; then
  OUTPUT_PATH=$(resolve_host_path "$OUTPUT_PATH")
else
  OUTPUT_PATH=$(default_export_path "$FORMAT")
  echo "No export path provided. Using default export path: $OUTPUT_PATH"
fi
ensure_parent_directory "$OUTPUT_PATH"

ensure_docker
compose up -d postgres
wait_for_postgres

container_id=$(db_container_id)
container_dump_path="/tmp/immich-export.dump"

case "$FORMAT" in
  custom)
    compose exec -T "$(db_service_name)" pg_dump \
      --clean \
      --if-exists \
      --format=custom \
      --username="${TESTBED_DB_USER:-postgres}" \
      --dbname="${TESTBED_DB_NAME:-immich}" \
      --file="$container_dump_path"
    ;;
  plain)
    compose exec -T "$(db_service_name)" sh -eu -c "
      pg_dump --clean --if-exists --username='${TESTBED_DB_USER:-postgres}' --dbname='${TESTBED_DB_NAME:-immich}' > '$container_dump_path'
    "
    ;;
  *)
    echo "ERROR: Unsupported export format: $FORMAT" >&2
    exit 1
    ;;
esac

docker cp "${container_id}:${container_dump_path}" "$OUTPUT_PATH"
compose exec -T "$(db_service_name)" rm -f "$container_dump_path"
echo "Export completed: $OUTPUT_PATH"
