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
requires CSRF protection for unsafe requests. Token login, document operations,
MinIO, RBAC, background jobs, and deployment configuration are not implemented yet.

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

Both require authentication and the `documents.view_file` permission.
Users can see their own files; superusers can see all files. Group-based
sharing and application admin roles will be added with RBAC.
Storage keys are excluded from API responses.

The Django admin registration is read-only until storage-aware write services
exist. Uploads, downloads, updates, deletion, and MinIO integration remain
unimplemented. No policy or claim relationship is assumed yet.

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
endpoint belong in settings. Upload/download APIs are still to be implemented.
