from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from extensions import db

class Log(db.Model):
    __tablename__ = 'logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_name = Column(String(255), nullable=False)  # 
    log_file_path = Column(String(500), nullable=False)  # 日志文件的存储路径（例如：本地文件路径或URL）
    created_at = Column(DateTime, default=datetime.utcnow)  # 日志文件的创建时间
    count = db.Column(db.Integer, default=1)  # 确保这里是 Integer

    def __repr__(self):
        return f'<Log {self.id} - {self.module_name}>'



class QueryRecord(db.Model):
    __tablename__ = 'query_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)  # 产品 ID
    module_id = Column(Integer, ForeignKey('modules.id'), nullable=False)  # 关联业务模块
    log_id = Column(Integer, ForeignKey('logs.id'), nullable=True)  # 关联上传日志
    log_file_path = Column(String(500), nullable=False)  # 日志文件存放地址
    branch_url = Column(String(500), nullable=False)  # 分支地址
    branch_version = Column(String(100), nullable=False)  # 分支版本
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
    answer = Column(Integer, nullable=True)  # 查询结果。0为成功，1为失败
    status = Column(String(32), nullable=True)
    log_hash = Column(String(64), nullable=True)
    error_fingerprint = Column(String(64), nullable=True, index=True)
    duration_ms = Column(Integer, nullable=True)
    model_name = Column(String(128), nullable=True)
    hit_cache = Column(Boolean, default=False)
    knowledge_case_id = Column(Integer, ForeignKey('analysis_knowledge_cases.id'), nullable=True)

    product = relationship("Product", backref="query_records")
    module = relationship("Module", backref="query_records")
    log = relationship("Log", backref="query_records")
    knowledge_case = relationship("AnalysisKnowledgeCase", backref="query_records")

    def __repr__(self):
        return f'<QueryRecord {self.id} - Product {self.product_id} - Module {self.module_id}>'


class AnalysisKnowledgeCase(db.Model):
    __tablename__ = 'analysis_knowledge_cases'
    __table_args__ = (
        UniqueConstraint('product_id', 'module_id', 'error_fingerprint', name='uq_knowledge_case_scope_fingerprint'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    module_id = Column(Integer, ForeignKey('modules.id'), nullable=False)
    error_fingerprint = Column(String(64), nullable=False, index=True)
    error_type = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    stack_top_file = Column(String(500), nullable=True)
    stack_top_line = Column(Integer, nullable=True)
    branch_url = Column(String(500), nullable=True)
    branch_version = Column(String(100), nullable=True)
    log_excerpt = Column(Text, nullable=True)
    code_files = Column(Text, nullable=True)
    code_snippets = Column(Text, nullable=True)
    issue_category = Column(String(64), nullable=False, default='unknown')
    conclusion_summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    ai_analysis = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, default=0)
    hit_count = Column(Integer, nullable=False, default=0)
    last_hit_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AnalysisKnowledgeCase {self.id} - {self.error_fingerprint}>'
