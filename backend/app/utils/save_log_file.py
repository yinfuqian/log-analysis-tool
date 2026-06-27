import os
from werkzeug.utils import secure_filename
from app.config import Config

def save_log_file(file, module_name):
    """ 根据存储类型（本地 / NAS / MinIO）保存日志文件 """
    filename = secure_filename(file.filename)

    if Config.STORAGE_TYPE == 'local':
        storage_path = os.path.join(Config.LOCAL_STORAGE_DIR, module_name)
        os.makedirs(storage_path, exist_ok=True)
        full_path = os.path.join(storage_path, filename)
        file.save(full_path)

    elif Config.STORAGE_TYPE == 'nas':
        storage_path = os.path.join(Config.NAS_STORAGE_PATH, module_name)
        os.makedirs(storage_path, exist_ok=True)
        full_path = os.path.join(storage_path, filename)
        file.save(full_path)

    elif Config.STORAGE_TYPE == 'minio':
        from minio import Minio
        
        minio_client = Minio(
            Config.MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
            access_key=Config.MINIO_ACCESS_KEY,
            secret_key=Config.MINIO_SECRET_KEY,
            secure=False
        )
        
        bucket_name = Config.MINIO_BUCKET_NAME
        minio_path = f"{module_name}/{filename}"
        
        # 确保存储桶存在
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        # 上传文件到 MinIO
        file.seek(0)  # 重新定位文件指针
        minio_client.put_object(
            bucket_name, minio_path, file, length=-1, part_size=10*1024*1024
        )
        full_path = f"{Config.MINIO_ENDPOINT}/{bucket_name}/{minio_path}"

    else:
        raise ValueError("未知的存储类型")

    return full_path
