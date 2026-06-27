from datetime import datetime

from extensions import db


class GitRef(db.Model):
    __tablename__ = "git_refs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ref_key = db.Column(db.String(64), nullable=False, unique=True)
    repo_url = db.Column(db.String(500), nullable=False, index=True)
    ref_name = db.Column(db.String(255), nullable=False)
    ref_type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<GitRef {self.repo_url} {self.ref_type}:{self.ref_name}>"
