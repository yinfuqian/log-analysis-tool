"""celery worker 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from app import create_app
from extensions import celery


flask_app = create_app()
celery_app = celery
