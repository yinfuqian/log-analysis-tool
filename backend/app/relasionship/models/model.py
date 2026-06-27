from datetime import datetime
from sqlalchemy import Column, Integer, DateTime
from extensions import db

class ProductModule(db.Model):
    __tablename__ = 'product_modules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False) 
    module_id = Column(Integer, nullable=False)   
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ProductModule {self.product_id}-{self.module_id}>'

class ModuleBranch(db.Model):
    __tablename__ = 'module_branches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, nullable=False) 
    branch_id = Column(Integer, nullable=False) 
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ModuleBranch {self.module_id}-{self.branch_id}>'
