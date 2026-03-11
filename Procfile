release: alembic upgrade head
web: uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --log-level info
worker: celery -A backend.celery_app:celery_app worker --loglevel=info --concurrency=4
beat: celery -A backend.celery_app:celery_app beat --loglevel=info
