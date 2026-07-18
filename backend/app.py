"""app 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_RUN_PORT", "5000")),
        threaded=True,
    )
