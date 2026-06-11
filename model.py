import os
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from extensions import db

import uuid

DB_TABLE_JOBS = os.environ.get('DB_TABLE_JOBS', 'jobs_storage')
DB_TABLE_FILE_MATCHES = os.environ.get('DB_TABLE_FILE_MATCHES', 'file_matches')

class JobStorage(db.Model):
    __tablename__ = DB_TABLE_JOBS
    jobid = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, autoincrement=False)
    archivename = db.Column(db.String, nullable=False)
    pattern = db.Column(db.String, nullable=False)
    status = db.Column(db.Enum('pending','running','completed','failed', name='job_status'), nullable=False, default='pending')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    error = db.Column(db.String, nullable=True)
#    files = db.relationship('FileMatch', backref='job', lazy=True)

class FileMatch(db.Model):
    __tablename__ = DB_TABLE_FILE_MATCHES
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    jobid = db.Column(UUID(as_uuid=True), db.ForeignKey(f'{DB_TABLE_JOBS}.jobid'), nullable=False, index=True)
    filepath = db.Column(db.String, nullable=False)
    filename = db.Column(db.String, nullable=False)
    filesize = db.Column(db.BigInteger, nullable=False)
    nesting_depth = db.Column(db.Integer, nullable=False)
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)
    source_archive = db.Column(db.String, nullable=False)
    nesting_chain = db.Column(db.String, nullable=False)