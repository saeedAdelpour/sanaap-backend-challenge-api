# Sanaap Backend Challenge API

Django 5.2 LTS and Django REST framework, managed with uv. Python 3.11 is
selected in `.python-version`. Application code lives in
`src/sanaap_backend_challenge_api/` and uv installs it as an editable package.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --locked
cp .env.example .env
uv run pre-commit install
# Set POSTGRES_* in .env to match your PostgreSQL database and role.
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

- Admin: http://127.0.0.1:8000/admin/
- Browsable API session login: http://127.0.0.1:8000/api-auth/login/
- Public liveness check: http://127.0.0.1:8000/api/health/

PostgreSQL 14+ is required. API views require authentication by
default; the liveness probe is explicitly public. Session authentication
requires CSRF protection for unsafe requests. Document deletion,
RBAC, background jobs, and application deployment configuration are not implemented yet.

## Database

Configure `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env`.
The server defaults to `localhost:5432`; override `POSTGRES_HOST` and
`POSTGRES_PORT` as needed. The database and login role must already exist,
and the role must have permission to create tables in the database schema.

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

Both endpoints require a DRF token. Authenticated users can currently access all file metadata; role checks are not implemented.
Storage keys are excluded from API responses.

The Django admin registration is read-only until storage-aware write services
exist. Downloads, updates, and deletion remain unimplemented. No policy or claim relationship is assumed yet.

Apply the schema with `uv run python manage.py migrate`.

## Local MinIO

MinIO runs in Docker while Django continues to run with uv. PostgreSQL remains
the existing external service. The pinned community image is for local development;
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

When Django is containerized later, use `MINIO_ENDPOINT=minio:9000` on the
Compose network. The File model already stores the object key; bucket and
endpoint belong in settings. Downloads are still to be implemented.

## Presigned uploads

File endpoints require token authentication (see below). The bucket remains
private. Delete is not implemented. New uploads record the authenticated user
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
This single-object flow supports up to 5 GiB. Content inspection and download
endpoints are not implemented. Content type remains generic.
Staging objects under `uploads/` are retained for now; lifecycle cleanup and
abandoned pending-record cleanup remain follow-up work.

Apply migrations before using the API:
`uv run python manage.py migrate`.

`MINIO_ENDPOINT` must be reachable by the client because it appears in the
signed URL. Do not rewrite the URL hostname after signing. Browser frontends
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

These endpoints require token authentication, matching the other file endpoints. Deletion remains unavailable. Old content and staging objects are
retained; existing download URLs may continue serving the old content until
expiry. Cleanup will be handled separately.

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
deployed login and API endpoints. Authentication identifies users; role and
file-level access restrictions are still pending.
