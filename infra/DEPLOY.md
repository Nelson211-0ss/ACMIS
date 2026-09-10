# Deploying ACMIS

The API and its Postgres cluster run as three containers behind the host's
nginx. This is the record of how the deployment on `147.224.178.246` was made
and how to change it, because the expensive part of a deployment is the part
nobody wrote down.

## Shape

```
browser ──▶ nginx :80  (host, name-based vhost *.147-224-178-246.sslip.io)
              └──▶ acmis-api :8100 → :8000   uvicorn, production mode
                     ├──▶ acmis-postgres     no published port
                     └──▶ acmis-redis        no published port
```

Only the API is reachable. Postgres and Redis have no `ports:` mapping at all
— they exist on the compose network and are addressed as `postgres` and
`redis`. On a host that already runs eight other applications, publishing a
database port is how one of them ends up talking to the wrong cluster.

## Tenant resolution is by hostname

ACMIS decides which university a request belongs to in this order: the `tid`
claim on a verified token, then the `Host` header, then `X-ACMIS-Tenant` —
**and the last only in `local`/`test`**. In production the header is ignored
on purpose: honouring it would let a signed-in user at one university address
another's database by editing a request.

So a deployed ACMIS needs real hostnames. `sslip.io` is public wildcard DNS
that resolves `<anything>.147-224-178-246.sslip.io` to `147.224.178.246`,
which gives host-based routing without buying a domain:

| host                                    | reaches                     |
| --------------------------------------- | --------------------------- |
| `demo.147-224-178-246.sslip.io`         | the `demo` tenant           |
| `admin.147-224-178-246.sslip.io`        | the control plane           |
| `147.224.178.246`                       | nothing — 404, by design    |

Onboarding a university needs no nginx change: the vhost is a wildcard and the
slug is looked up in the control-plane database at request time.

Point a real domain at the host and this becomes one variable —
`ACMIS_TENANT_HOST_SUFFIX` — plus the matching `server_name`.

## Files

| file                           | what it is                                        |
| ------------------------------ | ------------------------------------------------- |
| `docker-compose.prod.yml`      | the deployed stack                                |
| `docker-compose.yml`           | the laptop stack — publishes ports, weak creds    |
| `postgres-init.sql`            | extensions into `template1`, on first start       |
| `postgres-roles.sql`           | `acmis_auditor`, needed before a restore          |
| `../services/api/Dockerfile`   | the API image                                     |
| `.env`                         | **not in git.** Credentials. Mode 600.            |

`postgres-roles.sql` exists because `pg_dump` dumps grants but never the roles
they name. A restored tenant database whose audit tables
`GRANT SELECT ... TO acmis_auditor` fails on that grant unless the role is
already there.

## First deployment

```sh
# On the host, in ~/acmis/infra, with .env in place:
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml up -d postgres redis
# ... restore or migrate (below) ...
docker compose -f docker-compose.prod.yml up -d api
```

With an empty cluster and no dumps, create the schema and a demo tenant
instead of restoring:

```sh
docker compose -f docker-compose.prod.yml run --rm api python -m acmis.cli control-migrate
docker compose -f docker-compose.prod.yml run --rm api python -m acmis.cli demo
```

## Migrating data in

Dumps are taken with the *same major version* as the target cluster — both are
Postgres 17 — and restored inside the container so the client and server
versions match by construction.

```sh
# Source (laptop):
for db in acmis_control acmis_t_template acmis_t_demo; do
  docker exec acmis-postgres pg_dump -U acmis -d "$db" --format=custom -f "/tmp/$db.dump"
  docker cp "acmis-postgres:/tmp/$db.dump" "dumps/$db.dump"
done

# Target: the control database is created by the image entrypoint; tenant
# databases are not. TEMPLATE template1 so they inherit pgcrypto, pg_trgm and
# unaccent — a tenant database missing pg_trgm has student search silently
# fall back to a sequential scan there and nowhere else.
for db in acmis_t_template acmis_t_demo; do
  docker exec acmis-postgres psql -U acmis -d postgres \
    -c "CREATE DATABASE \"$db\" TEMPLATE template1 LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8'"
done
for db in acmis_control acmis_t_template acmis_t_demo; do
  docker cp "dumps/$db.dump" "acmis-postgres:/tmp/$db.dump"
  docker exec acmis-postgres pg_restore -U acmis -d "$db" --no-owner --exit-on-error "/tmp/$db.dump"
done
```

Two things to check afterwards, because both are silent failures:

```sh
# The 26 append-only rules that make the audit trail, the ledger and the
# ballot box unmodifiable. A restore that dropped them leaves a system that
# looks identical and cannot support an appeal.
docker exec acmis-postgres psql -U acmis -d acmis_t_demo -tAc \
  "select count(*) from pg_rules where rulename like '%\_no\_update' or rulename like '%\_no\_delete'"

# The double-entry ledger must sum to exactly zero.
docker exec acmis-postgres psql -U acmis -d acmis_t_demo -tAc \
  "select coalesce(sum(amount_minor),0) from ledger_entry"
```

The tenant row's `database_dsn` is left NULL deliberately. The DSN is built
from `ACMIS_TENANT_DATABASE_URL_TEMPLATE`, so rotating the cluster password is
one environment variable rather than one `UPDATE` per tenant database.

## Redeploying code

```sh
# from the repo root, on a machine that can reach the host:
tar --exclude='.venv' --exclude='__pycache__' --exclude='node_modules' \
    -czf /tmp/acmis.tgz services/api infra
scp /tmp/acmis.tgz dockeruser@147.224.178.246:~/acmis/
ssh dockeruser@147.224.178.246 'cd ~/acmis && tar xzf acmis.tgz && rm acmis.tgz &&
  cd infra && docker compose -f docker-compose.prod.yml build api &&
  docker compose -f docker-compose.prod.yml up -d api'
```

The tarball excludes `.venv`: several hundred megabytes of macOS-linked wheels
that would be both useless and wrong inside a Linux ARM64 image.

## Migrations

Schema changes ship as Alembic revisions in two trees — control and tenant —
and are applied from inside the API container:

```sh
docker compose -f docker-compose.prod.yml run --rm api python -m acmis.cli control-migrate
docker compose -f docker-compose.prod.yml run --rm api python -m acmis.cli migrate-all
```

`migrate-all` walks every tenant database. It is idempotent; running it when
everything is current is a no-op that prints the revision.

## Backups

Nothing is scheduled — deliberately, since an unmonitored backup is worse than
a known absence. The command to schedule is:

```sh
docker exec acmis-postgres pg_dumpall -U acmis | gzip > acmis-$(date -u +%Y%m%dT%H%M).sql.gz
```

Note `pg_dumpall`, not `pg_dump`: with database-per-tenant, a backup of one
database is a backup of one university.

## Health and logs

```sh
curl -s -H 'Host: demo.147-224-178-246.sslip.io' http://127.0.0.1/health/ready
docker logs -f acmis-api
docker compose -f docker-compose.prod.yml ps
tail -f /var/log/nginx/acmis.error.log
```

`/health/live` answers without touching Postgres or Redis, which is what the
container healthcheck uses: a database outage should not make Docker restart a
process that is working correctly and reporting the outage. `/health/ready`
does check both, and is the one to page on.

## Local apps against the deployed backend

The thirteen Next.js apps stay on `localhost:3000-3012` and take their data
from the VPS. Each app's `.env.local` holds:

```
ACMIS_API_URL=http://demo.147-224-178-246.sslip.io
ACMIS_API_INTERNAL_URL=http://demo.147-224-178-246.sslip.io
NEXT_PUBLIC_ACMIS_ENV=local
```

Two things make this work and are worth knowing before changing either.

**The subdomain in that URL is the tenant selector.** All API traffic goes
through the Next.js server, which uses plain `fetch`, so the `Host` header is
whatever the URL says — `demo.147-224-178-246.sslip.io`. That is what reaches
the demo tenant, because the deployed API ignores `X-ACMIS-Tenant`. The client
still sends that header and the API logs `tenant_header_ignored` and discards
it. Set the URL to `http://localhost:8000` to go back to a local API, where
the header is honoured again.

**`NEXT_PUBLIC_ACMIS_ENV` stays `local`.** It is the only browser-visible
variable, and it makes the module launcher link to `http://localhost:3001`
rather than to `/admissions` on a single deployed host. Data comes from the
VPS; navigation stays on the laptop.

CORS is not involved for page rendering — the apps call the API server to
server — but `ACMIS_CORS_ORIGINS` in `.env` lists `localhost:3000-3012`
anyway, so a browser-side call from a dev server works too.

## Still to do

- **TLS.** The vhost is plain HTTP. `certbot --nginx` cannot issue for
  `sslip.io` names at scale; this wants a real domain first.
- **The frontends.** Thirteen Next.js apps are not deployed. Each needs its
  own origin under the tenant suffix and `ACMIS_API_URL` pointed at
  `http://demo.147-224-178-246.sslip.io`.
- **Object storage.** `ACMIS_S3_*` is unset, so document upload has nowhere to
  put a file. The laptop stack uses MinIO; production wants a bucket.
- **Mail.** `ACMIS_SMTP_HOST` is unset, so password-reset and results
  notifications are logged and dropped.
