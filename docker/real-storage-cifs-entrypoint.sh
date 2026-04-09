#!/bin/sh
set -eu

if [ "${TESTBED_STORAGE_SOURCE_MODE:-mock}" != "real" ] || [ "${TESTBED_REAL_STORAGE_MODE:-}" != "cifs" ]; then
  exec /usr/local/bin/immich-doctor-entrypoint "$@"
fi

: "${TESTBED_REAL_STORAGE_SMB_SOURCE:?Set TESTBED_REAL_STORAGE_SMB_SOURCE for real CIFS mode}"
: "${TESTBED_REAL_STORAGE_SMB_USERNAME:?Set TESTBED_REAL_STORAGE_SMB_USERNAME for real CIFS mode}"
: "${TESTBED_REAL_STORAGE_SMB_PASSWORD:?Set TESTBED_REAL_STORAGE_SMB_PASSWORD for real CIFS mode}"

if [ "$(id -u)" -ne 0 ]; then
  echo "real-storage CIFS mode requires root inside the container" >&2
  exit 1
fi

mkdir -p /mnt/immich/storage

credentials_file="$(mktemp /tmp/immich-doctor-cifs-credentials.XXXXXX)"
cleanup() {
  rm -f "$credentials_file"
}
trap cleanup EXIT INT TERM

{
  printf 'username=%s\n' "$TESTBED_REAL_STORAGE_SMB_USERNAME"
  printf 'password=%s\n' "$TESTBED_REAL_STORAGE_SMB_PASSWORD"
  if [ -n "${TESTBED_REAL_STORAGE_SMB_DOMAIN:-}" ]; then
    printf 'domain=%s\n' "$TESTBED_REAL_STORAGE_SMB_DOMAIN"
  fi
} > "$credentials_file"
chmod 600 "$credentials_file"

mount_options="ro,credentials=$credentials_file,vers=${TESTBED_REAL_STORAGE_SMB_VERS:-3.0},uid=${TESTBED_REAL_STORAGE_SMB_UID:-1000},gid=${TESTBED_REAL_STORAGE_SMB_GID:-1000},file_mode=0444,dir_mode=0555"

mount -t cifs "$TESTBED_REAL_STORAGE_SMB_SOURCE" /mnt/immich/storage -o "$mount_options"
mount_line="$(mount | grep ' on /mnt/immich/storage type cifs ' || true)"

if [ -z "$mount_line" ]; then
  echo "real-storage CIFS mode did not produce a cifs mount at /mnt/immich/storage" >&2
  exit 1
fi

case "$mount_line" in
  *"(ro,"*|*",ro,"*|*",ro)"*)
    ;;
  *)
    echo "real-storage CIFS mount is not read-only: $mount_line" >&2
    exit 1
    ;;
esac

exec /usr/local/bin/immich-doctor-entrypoint "$@"
