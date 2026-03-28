#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

FORCE=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=true
      shift
      ;;
    --help|-h)
      echo "Usage: snapshot-db.sh [--force]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ensure_docker
confirm_or_exit "Overwrite snapshot volume $(snapshot_volume_name) from $(db_volume_name)?" "$FORCE"

require_volume "$(db_volume_name)" "Active database volume"
ensure_volume_exists "$(snapshot_volume_name)" "Snapshot volume"
echo "Stopping PostgreSQL for a consistent volume snapshot..."
compose stop "$(db_service_name)"
copy_volume_contents "$(db_volume_name)" "$(snapshot_volume_name)"
compose start "$(db_service_name)"
wait_for_postgres
echo "Snapshot completed: $(snapshot_volume_name)"
