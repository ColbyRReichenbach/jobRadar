release: alembic upgrade head
web: gunicorn -c gunicorn.conf.py backend.main:app
worker: celery -A backend.celery_app:celery_app worker --loglevel=info
beat: celery -A backend.celery_app:celery_app beat --loglevel=info
