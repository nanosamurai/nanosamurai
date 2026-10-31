# Upgrade local storage

Earlier versions of the Compose stack lost data on restart.
`docker compose down` followed by `up` started with an empty database.
Recordings and speaker-enrollment audio disappeared whenever the object store restarted.

This version stores both in named volumes:

| Data | Service | Volume | Mount |
| --- | --- | --- | --- |
| Sessions, transcripts, speakers | `postgres` | `nanosamurai_pgdata` | `/var/lib/postgresql` |
| Recordings, enrollment audio | `s3` ([versitygw](https://github.com/versity/versitygw)) | `nanosamurai_s3` | `/data` |

A new installation needs no extra steps.
If you already run the stack, follow this guide before you start the new version.
Otherwise the new version starts with an empty database and empty buckets.
Your old data stays on disk, but the new version does not use it.

## Why data was lost

PostgreSQL 18 images keep their data in `/var/lib/postgresql/18/docker`.
The old stack mounted `nanosamurai_pgdata` one level too deep, at `/var/lib/postgresql/data`.
The database went into an anonymous volume instead.
`docker compose up` gives a new container a new anonymous volume, so each `down` and `up` started with an empty database.
The old anonymous volume stays on disk until you delete it.

The old object store was LocalStack Community.
It ignores `PERSISTENCE=1` and keeps objects only in memory.
Its `nanosamurai_localstack` volume never held any objects.
Objects stored before LocalStack last restarted can't be recovered.
Their sessions remain, but their audio no longer plays.

## Before you start

- These commands use the default project name `nanosamurai`.
  If you set another name with `-p` or `COMPOSE_PROJECT_NAME`, replace the `nanosamurai` prefix in container, network, and volume names.
- Use the same Compose file list for every `docker compose` command, including your model overlays.
- Finish or stop active recordings.
- The commands work in Bash and PowerShell, except for the loop in [Recover a database after a restart](#recover-a-database-after-a-restart).

## Upgrade a running stack

Keep the old stack running until step 2. LocalStack holds your current objects only in memory.

1. Export the objects that LocalStack holds now:

   ```bash
   docker volume create nanosamurai_s3_export
   docker run --rm --network nanosamurai_default -v nanosamurai_s3_export:/export -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=us-east-1 --entrypoint sh amazon/aws-cli:2.39.2 -c 'for b in nanosamurai-recordings nanosamurai-enrollment xamurai-enrollment; do aws --endpoint-url http://localstack:4566 s3 sync --only-show-errors s3://$b /export/$b; done; find /export -type f | wc -l'
   ```

   The last line is the number of exported objects. It can be 0.

2. Stop the stack. Use `stop`, not `down`, so that the old Postgres container keeps its volume:

   ```bash
   docker compose -f docker-compose.yml stop
   ```

3. Find the anonymous volume with your database:

   ```bash
   docker container inspect -f '{{range .Mounts}}{{println .Destination .Name}}{{end}}' nanosamurai-postgres-1
   ```

   The name after `/var/lib/postgresql` is the anonymous volume, a long hexadecimal ID.
   The volume after `/var/lib/postgresql/data` should be `nanosamurai_nanosamurai_pgdata`.
   If the only mount is `/var/lib/postgresql nanosamurai_nanosamurai_pgdata`, your stack already uses the new layout. Skip to step 6.

4. Check that the named volume is empty:

   ```bash
   docker run --rm -v nanosamurai_nanosamurai_pgdata:/to alpine:3.20 ls -A /to
   ```

   The command should print nothing.
   If it prints `PG_VERSION` or `base`, see [A named volume has PostgreSQL 17 or older data](#a-named-volume-has-postgresql-17-or-older-data).

5. Copy the database into the named volume. Replace `<anonymous-volume>` with the ID from step 3:

   ```bash
   docker run --rm -v <anonymous-volume>:/from:ro -v nanosamurai_nanosamurai_pgdata:/to alpine:3.20 cp -a /from/18 /to/
   docker run --rm -v nanosamurai_nanosamurai_pgdata:/to:ro alpine:3.20 cat /to/18/docker/PG_VERSION
   ```

   The second command must print `18`.

6. Update your checkout. Then start the new version with your usual command:

   ```bash
   git pull
   docker compose -f docker-compose.yml up -d
   ```

7. Import the exported objects into the new object store:

   ```bash
   docker run --rm --network nanosamurai_default -v nanosamurai_s3_export:/export:ro -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=us-east-1 --entrypoint sh amazon/aws-cli:2.39.2 -c 'for b in nanosamurai-recordings nanosamurai-enrollment xamurai-enrollment; do aws --endpoint-url http://s3:7070 s3 sync --only-show-errors /export/$b s3://$b; done'
   ```

8. Open [Recordings](http://127.0.0.1:8000/recordings) and [Speakers](http://127.0.0.1:8000/speakers).
   Check that your sessions are listed and that a recent recording plays.

9. When everything works, delete the leftovers:

   ```bash
   docker volume rm <anonymous-volume> nanosamurai_s3_export nanosamurai_nanosamurai_localstack
   ```

## Recover a database after a restart

If you already ran `down` and `up` with the old stack, your sessions seem to be gone.
They are usually still in an older anonymous volume.
Don't run `docker volume prune` or `docker system prune --volumes` until you recover them.

List the unused volumes that hold a PostgreSQL 18 database, with their creation times.

Bash:

```bash
for v in $(docker volume ls -q -f dangling=true); do docker run --rm -v "$v:/v:ro" alpine:3.20 test -s /v/18/docker/PG_VERSION && echo "$v $(docker volume inspect -f '{{.CreatedAt}}' $v)"; done
```

PowerShell:

```powershell
foreach ($v in docker volume ls -q -f dangling=true) { docker run --rm -v "${v}:/v:ro" alpine:3.20 test -s /v/18/docker/PG_VERSION; if ($LASTEXITCODE -eq 0) { "$v " + (docker volume inspect -f '{{.CreatedAt}}' $v) } }
```

The loop starts one short container per unused volume, so it can take a few minutes.
Volumes from other Compose projects can appear too.
Each `down` and `up` left one volume, so pick the one created when the lost data was current.
Then follow [Upgrade a running stack](#upgrade-a-running-stack) from step 2.
In step 5, use the volume that you picked.
If you are not sure, copy each candidate into a new scratch volume and inspect it with a temporary `postgres:18.1-alpine` container before you choose.

## A named volume has PostgreSQL 17 or older data

If `nanosamurai_pgdata` holds files from PostgreSQL 17 or older, the new version doesn't start.
The `postgres` log says that there appears to be PostgreSQL data in `/var/lib/postgresql`.
The official image refuses to start rather than mix the two layouts.
This can happen if you reused a volume from another project.

Move the data to PostgreSQL 18 with a dump and restore:

1. Stop the stack and check the old major version:

   ```bash
   docker compose -f docker-compose.yml stop
   docker run --rm -v nanosamurai_nanosamurai_pgdata:/v:ro alpine:3.20 cat /v/PG_VERSION
   ```

2. Back up the volume. Then dump the database with the matching image, here PostgreSQL 17:

   ```bash
   docker volume create nanosamurai_pgdata_pg17_backup
   docker run --rm -v nanosamurai_nanosamurai_pgdata:/from:ro -v nanosamurai_pgdata_pg17_backup:/to alpine:3.20 cp -a /from/. /to/
   docker volume create nanosamurai_pgdump
   docker run -d --name nanosamurai-pg-old -v nanosamurai_nanosamurai_pgdata:/var/lib/postgresql/data -v nanosamurai_pgdump:/dump postgres:17-alpine
   docker exec nanosamurai-pg-old pg_dump -U nanosamurai -d nanosamurai -Fc -f /dump/nanosamurai.dump
   docker rm -f nanosamurai-pg-old
   ```

   Wait a few seconds after `docker run` so that the server is ready before you run `pg_dump`.

3. Remove the old volume. Start only Postgres so that it creates an empty PostgreSQL 18 database. Then restore the dump:

   ```bash
   docker compose -f docker-compose.yml rm -f postgres
   docker volume rm nanosamurai_nanosamurai_pgdata
   docker compose -f docker-compose.yml up -d postgres
   docker run --rm --network nanosamurai_default -e PGPASSWORD=nanosamurai -v nanosamurai_pgdump:/dump:ro postgres:18.1-alpine pg_restore -h postgres -U nanosamurai -d nanosamurai --no-owner /dump/nanosamurai.dump
   ```

4. Start the stack with your usual command. Delete `nanosamurai_pgdump` and `nanosamurai_pgdata_pg17_backup` once your data is back.

## What else changed

- `s3` serves the S3 API on `http://s3:7070` inside the Compose network and on `127.0.0.1:7070` on the host.
  It uses the same local credentials as before (`test` / `test`).
- `s3_init` creates the buckets and then exits with code 0.
- `localstack` now serves only the Secrets Manager API for the webhook secret store, which is idle in Community Edition mode.
  It no longer publishes port 4566 on the host.
  LocalStack Community doesn't persist secrets either.
- If a local overlay sets `S3_ENDPOINT`, `ENROLL_S3_ENDPOINT`, or `SAMURAIBFF_S3_ENDPOINT` to `http://localstack:4566`, change it to `http://s3:7070`.
  If a service depends on `localstack` for object storage, make it depend on `s3_init` with `condition: service_completed_successfully`.
