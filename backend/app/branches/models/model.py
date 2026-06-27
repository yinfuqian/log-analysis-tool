from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from extensions import db

class Branch(db.Model):
    __tablename__ = 'branches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    address = Column(String(255), nullable=False)
    tag_version = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Branch {self.name}>'
