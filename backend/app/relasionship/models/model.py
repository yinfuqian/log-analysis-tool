"""model 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime
from extensions import db

class ProductModule(db.Model):
    """ProductModule 类封装该领域对象的状态、依赖与相关行为。"""
    __tablename__ = 'product_modules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False) 
    module_id = Column(Integer, nullable=False)   
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        """返回便于日志记录和调试查看的对象表示。"""
        return f'<ProductModule {self.product_id}-{self.module_id}>'

class ModuleBranch(db.Model):
    """ModuleBranch 类封装该领域对象的状态、依赖与相关行为。"""
    __tablename__ = 'module_branches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, nullable=False) 
    branch_id = Column(Integer, nullable=False) 
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        """返回便于日志记录和调试查看的对象表示。"""
        return f'<ModuleBranch {self.module_id}-{self.branch_id}>'
