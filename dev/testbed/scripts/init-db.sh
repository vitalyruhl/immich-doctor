#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

MODE="${TESTBED_INIT_MODE:-FROM_DUMP}"
DUMP_PATH="${TESTBED_DUMP_PATH:-}"
DUMP_FORMAT="${TESTBED_DUMP_FORMAT:-auto}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --dump)
      DUMP_PATH="$2"
      shift 2
      ;;
    --format)
      DUMP_FORMAT="$2"
      shift 2
      ;;
    --help|-h)
      cat <<'EOF'
Usage: init-db.sh [--mode FROM_DUMP|EMPTY] [--dump /path/to/file] [--format auto|plain|custom]
EOF
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ensure_docker
echo "Starting PostgreSQL testbed..."
compose up -d postgres
wait_for_postgres

case "$MODE" in
  FROM_DUMP|from-dump|from_dump)
    if [ -z "$DUMP_PATH" ]; then
      echo "ERROR: TESTBED_DUMP_PATH or --dump is required for FROM_DUMP mode." >&2
      exit 1
    fi
    restore_dump_into_database "$DUMP_PATH" "$DUMP_FORMAT"
    ;;
  EMPTY|empty)
    echo "Leaving database empty as requested."
    ;;
  *)
    echo "ERROR: Unsupported mode: $MODE" >&2
    exit 1
    ;;
esac

echo "Testbed initialization complete."
