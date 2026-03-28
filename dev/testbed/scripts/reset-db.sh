#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

FORCE=false
REMOVE_SNAPSHOT=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=true
      shift
      ;;
    --remove-snapshot)
      REMOVE_SNAPSHOT=true
      shift
      ;;
    --help|-h)
      echo "Usage: reset-db.sh [--force] [--remove-snapshot]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ensure_docker
confirm_or_exit "Reset the active testbed database volume $(db_volume_name)? This destroys current DB state." "$FORCE"

compose down --remove-orphans
remove_volume_if_exists "$(db_volume_name)" "Active database volume"
if [ "$REMOVE_SNAPSHOT" = "true" ]; then
  confirm_or_exit "Also delete snapshot volume $(snapshot_volume_name)?" "$FORCE"
  remove_volume_if_exists "$(snapshot_volume_name)" "Snapshot volume"
fi
ensure_volume_exists "$(db_volume_name)" "Active database volume"
compose up -d postgres
wait_for_postgres
echo "Reset completed. The database volume is now empty."
