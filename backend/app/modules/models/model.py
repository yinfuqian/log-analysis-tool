"""model 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from extensions import db
class Module(db.Model):
    """Module 类封装该领域对象的状态、依赖与相关行为。"""
    __tablename__ = 'modules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    branch = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        """返回便于日志记录和调试查看的对象表示。"""
        return f'<Module {self.name}>'
