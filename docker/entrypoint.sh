#!/bin/sh
set -eu

# Management commands run directly without repeating web-server initialization.
if [ "${1:-}" = "gunicorn" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi
exec "$@"
