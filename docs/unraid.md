# Unraid Install Guide

## Goal

This stack is designed for safe runtime validation on Unraid.
It does not build locally and does not perform destructive actions by default.

The container should run as non-root by default and mount Immich storage read-only.
For Unraid, prefer the published image `ghcr.io/vitalyruhl/immich-doctor:latest` instead of a local build.

------------------------------------------------------------

## Required files

You need:

- the contents of `docker/docker-compose.unraid.yml`
- environment values for all `${...}` variables used in that compose file

If the repository does not provide `.env.unraid.example`, create the environment values manually in Unraid using the `ENV FILE` editor.

------------------------------------------------------------

## Real Unraid GUI workflow

### Step 1 — Create the stack

Open:

Docker -> Compose -> Add New Stack

Enter:

stack name: immich-doctor

Optional:
choose a custom stack directory under Advanced
or leave the default value

Click:

OK

------------------------------------------------------------

### Step 2 — Edit the stack

After the stack is created, open:

Edit Stack

You will see:

- COMPOSE FILE
- ENV FILE
- UI LABELS
- STACK SETTINGS

------------------------------------------------------------

### Step 3 — Paste the compose file

Open:

COMPOSE FILE

Paste the full contents of:

docker/docker-compose.unraid.yml

Click:

OK

------------------------------------------------------------

### Step 4 — Fill the environment values

Open:

ENV FILE

If your compose file contains variables like:

${PUID}
${PGID}
${HOST_IMMICH_STORAGE_PATH}
${IMMICH_DOCTOR_IMAGE}

then those values must be defined here.

Example ENV FILE contents:

PUID=99
PGID=100
UMASK=002

IMMICH_DOCTOR_IMAGE=ghcr.io/vitalyruhl/immich-doctor:latest

HOST_IMMICH_STORAGE_PATH=/mnt/user/images/immich
HOST_BACKUP_TARGET_PATH=/mnt/user/backups/immich-doctor
HOST_REPORTS_PATH=/mnt/user/appdata/immich-doctor/reports
HOST_MANIFESTS_PATH=/mnt/user/appdata/immich-doctor/manifests
HOST_QUARANTINE_PATH=/mnt/user/appdata/immich-doctor/quarantine
HOST_LOG_PATH=/mnt/user/appdata/immich-doctor/logs
HOST_TMP_PATH=/mnt/user/appdata/immich-doctor/tmp
HOST_CONFIG_PATH=/mnt/user/appdata/immich-doctor/config

DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_CONNECT_TIMEOUT_SECONDS=3

Replace:

<REPO_OWNER>

with the actual GitHub owner or a full image path.

If you do not want database validation yet, leave the DB fields empty.

Click:

OK

------------------------------------------------------------

### Step 5 — UI Labels

Open:

UI LABELS

These fields are optional.

You can leave them empty.

Optional examples:

Icon:
https://raw.githubusercontent.com/<REPO_OWNER>/<REPO_NAME>/main/docs/icon.png

Web UI:
(blank)

Shell:
/bin/sh

If you are unsure, leave all fields empty and click:

OK

------------------------------------------------------------

### Step 6 — Deploy the stack

After Compose File and Env File are filled in, deploy or start the stack from the Unraid Compose UI.

------------------------------------------------------------

## Required folders on Unraid

Create these folders first if they do not exist:

mkdir -p /mnt/user/appdata/immich-doctor
mkdir -p /mnt/user/appdata/immich-doctor/reports
mkdir -p /mnt/user/appdata/immich-doctor/manifests
mkdir -p /mnt/user/appdata/immich-doctor/quarantine
mkdir -p /mnt/user/appdata/immich-doctor/logs
mkdir -p /mnt/user/appdata/immich-doctor/tmp
mkdir -p /mnt/user/appdata/immich-doctor/config
mkdir -p /mnt/user/backups/immich-doctor

------------------------------------------------------------

## Notes about ENV FILE vs hardcoded values

If the compose file uses `${VARIABLE}` syntax, those values are not stored inside the compose file itself.
They must come from:

- the ENV FILE in Unraid
- or a `.env` file
- or direct hardcoded values inside the compose file

So no, not everything is automatically inside the compose file if variables are used.

------------------------------------------------------------

## Notes about UI Labels

UI Labels are only for convenience in the Unraid interface.

They are not required for the container to run.

You can safely leave them empty.

Typical meaning:

- Icon: optional image URL shown in UI
- Web UI: optional URL opened from the UI
- Shell: optional shell path inside the container, for example `/bin/sh`

If the container image has no shell or you are not sure, leave it empty.

------------------------------------------------------------

## Check logs

After start, open:

Docker -> immich-doctor -> Logs

Expected output should indicate that runtime validation completed successfully.

------------------------------------------------------------

## Manual validation

If needed, run manually:

docker exec -it immich-doctor python -m immich_doctor runtime validate
