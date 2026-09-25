# Sanaap Backend Challenge API

Django 5.2 LTS and Django REST framework, managed with uv. Python 3.11 is
selected in `.python-version`. Application code lives in
`src/sanaap_backend_challenge_api/` and uv installs it as an editable package.

## Docker setup

Copy `.env.example` to `.env` if you do not already have one. Set
`POSTGRES_PASSWORD`, `MINIO_SECRET_KEY` (at least eight characters), and a unique
`DJANGO_SECRET_KEY`. Keep `127.0.0.1` in `DJANGO_ALLOWED_HOSTS` for health checks.
Docker Compose creates a PostgreSQL database using `POSTGRES_DB` and
`POSTGRES_USER`; it does not import an existing external database.

```sh
docker compose up -d --build --wait
docker compose exec backend python manage.py init_minio --configure-upload-lifecycle
docker compose exec backend python manage.py createsuperuser
```

Open http://localhost:8000/api/health/ or http://localhost:8000/admin/.
Nginx forwards requests to Gunicorn and serves collected static files.
The backend runs as a non-root user, applies migrations and collects static files
before Gunicorn starts. PostgreSQL and MinIO must be healthy before the backend
starts; Nginx waits for the backend health check. The health endpoint checks
liveness only, not ongoing database or storage availability.

`HTTP_PORT` changes the published API port; the example sets `HTTP_BIND_ADDRESS`
to `127.0.0.1`. `NGINX_PORT=80` sets the container port, Nginx listener, and
health-check port together. `HTTP_PROTOCOL=tcp` selects the transport; keep TCP
for this HTTP configuration. Nginx generates its config from
`docker/nginx/default.conf.template` at startup. Only Nginx and the existing local MinIO ports are published;
PostgreSQL and Gunicorn are accessible within the Compose network.
PostgreSQL, the backend, MinIO, and Nginx load all service environment variables from
`.env` using `env_file`, with no inline `environment` overrides. The example uses
`DJANGO_DEBUG=false`, `POSTGRES_HOST=postgres`, and `MINIO_ENDPOINT=minio:9000`
for Docker networking. MinIO's `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` expand
from the application credentials in the same file, so edit `MINIO_ACCESS_KEY`
and `MINIO_SECRET_KEY` to keep them synchronized. All four services receive the
file's variables. Your `.env` is supplied at runtime and excluded from the image. Dependencies are installed from `uv.lock` using
[uv's Docker workflow](https://docs.astral.sh/uv/guides/integration/docker/).

MinIO remains available at http://localhost:9000 and its console at
http://localhost:9001. `MINIO_ENDPOINT=minio:9000` is used internally, while
`MINIO_PUBLIC_ENDPOINT=localhost:9000` is used to sign browser-accessible URLs.
Signing uses `MINIO_REGION` (default `us-east-1`); match it to your storage region.
For remote access, configure a client-reachable MinIO address, its matching
`MINIO_PUBLIC_SECURE` setting, and published ports or TLS routing. Also configure
Django's allowed hosts and HTTPS termination before deploying publicly.
Do not rewrite signed URL hostnames after signing.

Useful commands:

```sh
docker compose logs -f backend nginx
docker compose exec backend python manage.py check
docker compose exec backend python manage.py test sanaap_backend_challenge_api
docker compose exec backend python manage.py purge_deleted_files
docker compose down
```

Schedule `docker compose exec -T backend python manage.py purge_deleted_files`
separately for retention cleanup. Database, object storage, and static files use
named volumes and survive `docker compose down`. **`docker compose down -v`
deletes these volumes and their data.** Database credentials initialize a new
volume only; changing `.env` does not change an existing database role/password.
Rebuild with `docker compose up -d --build --wait` after changing code or dependencies.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --locked
cp .env.example .env
uv run pre-commit install
# Set POSTGRES_* in .env to match your external PostgreSQL database and role.
# For host-based Django, set POSTGRES_HOST=localhost and MINIO_ENDPOINT=localhost:9000.
# Optionally set DJANGO_DEBUG=true for local development.
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

- Admin: http://127.0.0.1:8000/admin/
- Browsable API session login: http://127.0.0.1:8000/api-auth/login/
- Public liveness check: http://127.0.0.1:8000/api/health/

PostgreSQL 14+ is required. API views require authentication by
default; the liveness probe is explicitly public. Session authentication
requires CSRF protection for unsafe requests. Document endpoints use token authentication and group permissions.
Schedule the cleanup command described below separately from the web server.

## Database

Configure `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env`.
The Docker example uses `postgres:5432`; for host-based Django, set
`POSTGRES_HOST=localhost` and adjust `POSTGRES_PORT` as needed. Compose creates
the database and role. For an external PostgreSQL service, create them yourself
and give the role permission to create tables in the database schema.

Run `uv run python manage.py migrate` to initialize the database.
Existing SQLite data is not automatically copied to PostgreSQL.

## Dependency workflow

```sh
uv add package-name
uv add --dev development-tool
uv lock --upgrade-package package-name
uv sync --locked
```

Commit both `pyproject.toml` and `uv.lock`. Do not commit `.venv/`, `.env`,
or the local database. Use `uv run` rather than installing packages with pip;
manual virtual environment activation is unnecessary. `--locked` rejects a
stale lockfile rather than silently changing dependency resolution.

## Pre-commit

Install hooks once per clone with `uv run pre-commit install` after
`uv sync --locked`. Hooks run on staged files at commit time:

- Ruff linting (including import sorting) and formatting.
- File checks for whitespace, missing final newlines, YAML/TOML syntax,
  merge conflicts, filename case conflicts, large files, and private keys.
- Bandit security analysis of Python files.

Run all tracked files manually:

```sh
uv run pre-commit run --all-files
```

If a hook changes files, review and stage the changes, then rerun.
Hook tools use isolated environments with versions pinned in
`.pre-commit-config.yaml`; first use requires network access.
Update those versions intentionally with `uv run pre-commit autoupdate`.

## Checks

```sh
uv run python manage.py check
uv run python manage.py test sanaap_backend_challenge_api
```

Settings use `python-decouple` to load the root `.env` automatically; environment
variables override file values. No `--env-file` flag is needed.
Django requires `DJANGO_SECRET_KEY`; debug defaults to false when unset.
Use a unique secret and appropriate hosts for deployment. The development
server and example environment are for local use only.

## Original project brief

we want to design api for upload insurance documents


# functional requirements

- user can view/update/upload a file
- user can authenticate
- admin user has full access to all files
- editor user can upload and update file, but not delete
- viewer user can view file
- file url must be secure
- user can filter by file and choose what file wants
- files must be remove secure
 - what is secure? soft delete?

# non-functional requirements
- must use MinIO for object storage
- RBAC
- tests (unit/integration/e2e)
- api swagger
- complete readme file
- dockerize
    - ci/cd: github action
    - use nginx + gunicorn
- background tasks for file upload
- audit log for files
- websocket (saeed: or sse) for notify all users that a file uploaded

# core entities
user
file


# api
GET     /file/

GET     /file/<:file_id> return {url}

POST    /file/
{
    action: upload
    ???
}
return {file_id, pre_sign_url}

POST    /file/
{
    file_id
    action: update
}

POST    /login/ return token
{
    username
    password
}

## File skeleton

The `documents.File` model stores a UUID, title, original filename, private
storage key, content type, byte size, uploader, upload status, and timestamps.
The uploader is protected from deletion while referenced by a file.
Content type and byte size must be verified against the actual content by the
future upload service; metadata alone does not validate a file.

- `GET /api/files/`: paginated file metadata.
- `GET /api/files/{uuid}/`: individual file metadata.

Both endpoints require a DRF token. Users with the view permission can access file metadata.
Storage keys are excluded from API responses.

The Django admin registration is read-only until storage-aware write services
exist. Downloads, metadata updates, replacement, and soft deletion use API services. No policy or claim relationship is assumed yet.

Apply the schema with `uv run python manage.py migrate`.

## Local MinIO

For the host-based setup, run only MinIO in Docker and run Django with uv
against your external PostgreSQL service. The full container setup is above. The pinned community image is for local development;
the upstream community repository is archived, so reassess the distribution
before production deployment.

Set the `MINIO_*` values from `.env.example` in your local `.env`.
Generate a secret for `MINIO_SECRET_KEY`, for example with
`uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`.
The initial local setup already generated one in this checkout.

```sh
docker compose up -d --wait minio
uv run python manage.py init_minio
```

- S3 endpoint: http://localhost:9000
- Console: http://localhost:9001 (log in with the local MinIO access/secret keys)
- Bucket: `insurance-documents`

The initialization command is repeatable and creates a bucket without public
access. It refuses existing bucket policies for manual review. No bucket is
created automatically during Django startup.

Compose uses the configured keys as MinIO root credentials for local development.
Use a separate bucket-scoped application identity in production. Never publish
these credentials or grant anonymous access to insurance documents.
`MINIO_SECURE=false` is for local HTTP only; the settings default to TLS.

Data persists in the `minio_data` named volume across container restarts and
`docker compose down`. `docker compose down -v` deletes that stored data.

The Docker backend uses `MINIO_ENDPOINT=minio:9000` on the Compose network
and `MINIO_PUBLIC_ENDPOINT` for presigned uploads and downloads. The File model
stores the object key; bucket and endpoints belong in settings.

## Presigned uploads

File endpoints require token authentication (see below). The bucket remains
private. Deletion is described below. New uploads record the authenticated user
in `uploaded_by`; existing anonymous uploads keep their null uploader.

1. Request an upload URL:

   ```sh
   curl -X POST http://localhost:8000/api/files/ \
     -H 'Content-Type: application/json' \
     -d '{"original_name":"policy.pdf","size_bytes":1330,"title":"My policy"}'
   ```

   Use the actual byte size. The response contains the file `id`,
   `status=pending`, `upload_url`, `upload_method=PUT`, and `expires_in`.
   URLs expire after 300 seconds by default (`MINIO_UPLOAD_URL_TTL`).

2. Send raw file bytes directly to the returned URL, without Django credentials:

   ```sh
   curl --fail -X PUT --upload-file ./policy.pdf 'UPLOAD_URL_FROM_RESPONSE'
   ```

3. Confirm completion:

   ```sh
   curl --fail -X POST http://localhost:8000/api/files/FILE_ID/complete/
   ```

Completion checks the uploaded size, then copies the object inside MinIO to
a separate final key and marks it ready. File bytes never pass through Django.
Repeated completion is idempotent. Reusing an unexpired upload URL only changes
the staging object, not the ready document. Missing objects or size mismatches
return 400; storage failures return 503 and can be retried.

The declared size is validated on completion, not enforced during the PUT.
This single-object flow supports up to 5 GiB. Content inspection is not implemented. Content type remains generic.
Staging cleanup is configured separately below. Abandoned pending database
records are retained; expired uploads cannot be completed.

Apply migrations before using the API:
`uv run python manage.py migrate`.

`MINIO_PUBLIC_ENDPOINT` (defaulting to `MINIO_ENDPOINT` outside Compose) must
be reachable by the client because it appears in the signed URL. Do not rewrite the URL hostname after signing. Browser frontends
on another origin may also need MinIO CORS configuration.

## Modify an existing file

Metadata changes are immediate:

```http
PATCH /api/files/{id}/
Content-Type: application/json

{"title": "Updated policy", "original_name": "policy-renamed.pdf"}
```

Both fields are optional. Byte size, storage key, status, and uploader cannot
be changed through this endpoint. PUT on the file detail is not implemented.

To replace the content while keeping the same file ID:

1. `POST /api/files/{id}/replace/` with JSON:
   `{"original_name": "new-policy.pdf", "size_bytes": 1330}`.
2. PUT raw bytes to the returned `upload_url`.
3. `POST /api/files/{id}/replace/complete/` with JSON:
   `{"replacement_id": "UUID_FROM_STEP_1"}`.

The existing file remains ready and downloadable until step 3 succeeds.
Completion updates the original filename and byte size, preserving the title
and file ID. Repeated completion does not reapply a replacement.
A competing replacement completed in the meantime causes a 409; start a fresh
replacement. An ID belonging to another file returns 404.

These endpoints require token authentication. Old content is retained until the
file is deleted and its retention window passes. Existing download URLs may
continue serving old content until expiry. Temporary uploads have separate
lifecycle cleanup.

## Token authentication

Create a user with `uv run python manage.py createsuperuser`, or use an existing
active Django user. Obtain a DRF token:

```http
POST /api/login/
Content-Type: application/json

{"username": "your-username", "password": "your-password"}
```

The response is `{"token": "..."}`. Include it on every Django file API request:

```http
Authorization: Token YOUR_TOKEN
```

In Postman, add this header manually (the prefix is `Token`, not `Bearer`).
File endpoints require a token even when you are logged into Django admin.
Token-authenticated requests do not need CSRF tokens. Django admin continues
to use session authentication. The health endpoint remains public.

Do not send the Django token when uploading/downloading directly through a
MinIO presigned URL; that URL already authorizes the transfer.

Tokens are database-backed, one per user, and do not expire automatically.
They can be revoked by deleting their entry in Django admin. Use HTTPS for
deployed login and API endpoints. Admin users can delete files; Editors can upload and update; Viewers can read
and download. Permissions apply across files, without per-owner restrictions.


## Soft deletion and retention

`DELETE /api/files/{id}/` requires a token with `documents.destroy_file`
(the Admin group has this permission). It returns 204 and records `deleted_at`
and `deleted_by` without contacting MinIO. Deleted files disappear from all file
endpoints; subsequent requests, including another DELETE, return 404. Existing
presigned download URLs remain usable until expiry (300 seconds by default).
Upload completion and replacement cannot reactivate deleted files.

Active documents never expire under this application's cleanup policy.
`FILE_RETENTION_DAYS=30` controls retention **from API deletion**, not upload.
Changing this setting also changes the cutoff for previously deleted files.
After the window, cleanup removes the current and previous replacement objects,
including incomplete replacement copies, and records `purged_at`. Database
metadata stays for auditing. Restoration is not exposed by this API.

Apply the migration and configure staging cleanup:

```sh
uv run python manage.py migrate
uv run python manage.py init_minio --configure-upload-lifecycle
```

The latter installs/replaces only the `sanaap-staging-uploads` lifecycle rule,
filtered to `uploads/`, preserving other rules. Review any existing bucket rules
separately: an independently configured rule could still expire active documents.
Staging objects expire after `MINIO_STAGING_EXPIRATION_DAYS=8` days from creation.
New uploads and replacements must complete within `FILE_UPLOAD_COMPLETION_TTL=86400`
seconds of initiation; already completed requests remain idempotent. Lifecycle
expiration must be longer than both the completion deadline and upload URL TTL.
MinIO processes lifecycle expiration asynchronously. Original staging keys are
cleaned by this rule, including keys no longer referenced after completion.

Schedule the following command hourly using cron, a systemd timer, or your
platform's scheduler (use absolute paths and the configured application environment):

```sh
uv run python manage.py purge_deleted_files
```

Example crontab, replacing the installation paths:

```cron
0 * * * * cd /path/to/sanaap-backend-challenge-api && /path/to/uv run python manage.py purge_deleted_files
```

Cleanup is retry-safe: missing objects count as success, storage failures leave
`purged_at` unset, other eligible files are still processed, and the command exits
unsuccessfully so monitoring can detect the failure. Overlapping workers serialize
on each file's database lock. Bytes are removed on the first successful cleanup
run after the retention deadline, rather than at an exact instant.

Both cleanup and staging lifecycle setup require an unversioned bucket and refuse
buckets with enabled or suspended versioning. Version-aware deletion is not
implemented. No scheduler is started by Django; deployment must arrange the job.
