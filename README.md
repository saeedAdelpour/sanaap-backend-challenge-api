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
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

- Admin: http://127.0.0.1:8000/admin/
- Browsable API session login: http://127.0.0.1:8000/api-auth/login/
- Public liveness check: http://127.0.0.1:8000/api/health/

SQLite is used for local development. API views require authentication by
default; the liveness probe is explicitly public. Session authentication
requires CSRF protection for unsafe requests. Token login, document operations,
MinIO, RBAC, background jobs, and deployment configuration are not implemented yet.

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
