FROM ghcr.io/astral-sh/uv:0.12.10 AS uv
FROM python:3.11-slim-bookworm

COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
# Keep dependency installation cached when application code or docs change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY manage.py README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /app/staticfiles \
    && chown app:app /app/staticfiles
COPY docker/entrypoint.sh /entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/entrypoint.sh"]
CMD ["gunicorn", "sanaap_backend_challenge_api.config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
