#!/bin/sh
set -eu

umask "${UMASK:-002}"

exec "$@"
