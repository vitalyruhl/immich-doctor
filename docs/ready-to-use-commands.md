# Ready-To-Use Commands

This file is the canonical command reference for operators and contributors.

Rule:

- every finished user-facing command must be added here
- every renamed command must be updated here
- every deprecated or removed command must be removed here in the same change
- command examples in other docs should stay aligned with this file

## Runtime

```bash
docker exec -it immich-doctor python -m immich_doctor runtime health check
docker exec -it immich-doctor python -m immich_doctor runtime validate
docker exec -it immich-doctor python -m immich_doctor runtime integrity inspect
docker exec -it immich-doctor python -m immich_doctor runtime metadata-failures inspect
docker exec -it immich-doctor python -m immich_doctor runtime metadata-failures repair
docker exec -it immich-doctor python -m immich_doctor runtime metadata-failures repair --diagnostic-id metadata_failure:asset-123 --fix-permissions --apply
```

## Catalog Scan Lifecycle Controls

These commands call the running API runtime and expose true scan-job control
capabilities. Runtime worker resize is currently **next-run-only**.

```bash
docker exec -it immich-doctor python -m immich_doctor analyze catalog scan-job status
docker exec -it immich-doctor python -m immich_doctor analyze catalog scan-job start --force
docker exec -it immich-doctor python -m immich_doctor analyze catalog scan-job pause
docker exec -it immich-doctor python -m immich_doctor analyze catalog scan-job resume
docker exec -it immich-doctor python -m immich_doctor analyze catalog scan-job stop
docker exec -it immich-doctor python -m immich_doctor analyze catalog scan-job workers --workers 8
```

## Storage

```bash
docker exec -it immich-doctor python -m immich_doctor storage paths check
docker exec -it immich-doctor python -m immich_doctor storage permissions check
```

## Backup

Primary manual backup execution currently runs through the backup UI/API target
workflow.

`backup files` remains available, but it is legacy.

```bash
docker exec -it immich-doctor python -m immich_doctor backup files
docker exec -it immich-doctor python -m immich_doctor backup verify
docker exec -it immich-doctor python -m immich_doctor backup restore simulate --repair-run-id <repair-run-id>
docker exec -it immich-doctor python -m immich_doctor backup restore simulate --snapshot-id <snapshot-id>
```

## Repair

```bash
docker exec -it immich-doctor python -m immich_doctor repair undo plan --repair-run-id <repair-run-id>
docker exec -it immich-doctor python -m immich_doctor repair undo apply --repair-run-id <repair-run-id>
```

## Consistency

```bash
docker exec -it immich-doctor python -m immich_doctor consistency validate
docker exec -it immich-doctor python -m immich_doctor consistency repair --category db.orphan.album_asset.missing_asset
docker exec -it immich-doctor python -m immich_doctor consistency repair --all-safe --apply
```

## Database

```bash
docker exec -it immich-doctor python -m immich_doctor db health check
docker exec -it immich-doctor python -m immich_doctor db performance indexes check
```

## Remote Sync

```bash
docker exec -it immich-doctor python -m immich_doctor remote sync validate
docker exec -it immich-doctor python -m immich_doctor remote sync repair
docker exec -it immich-doctor python -m immich_doctor remote sync repair --apply
```
