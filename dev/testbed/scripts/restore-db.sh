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
      echo "Usage: restore-db.sh [--force]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ensure_docker
confirm_or_exit "Restore $(db_volume_name) from snapshot $(snapshot_volume_name)? This overwrites the active database volume." "$FORCE"

compose down --remove-orphans
copy_volume_contents "$(snapshot_volume_name)" "$(db_volume_name)"
compose up -d postgres
wait_for_postgres
echo "Restore completed from $(snapshot_volume_name)."
