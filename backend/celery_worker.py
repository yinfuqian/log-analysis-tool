from app import create_app
from extensions import celery


flask_app = create_app()
celery_app = celery
