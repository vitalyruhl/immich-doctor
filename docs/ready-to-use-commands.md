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
```

## Storage

```bash
docker exec -it immich-doctor python -m immich_doctor storage paths check
docker exec -it immich-doctor python -m immich_doctor storage permissions check
```

## Backup

```bash
docker exec -it immich-doctor python -m immich_doctor backup verify
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
